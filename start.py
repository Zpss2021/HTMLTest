#!/usr/bin/python
# -*- coding: utf-8

import SimpleHTTPServer
import BaseHTTPServer
import time
import SocketServer
import os
import threading
import socket
import re

#下面的导入从SimpleHTTPServer.py复制：
import posixpath
import urllib
import urlparse
import cgi
import sys
import shutil
import mimetypes
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

PORT = 80

class MyThreadingHTTPServer(SocketServer.ThreadingTCPServer):

    allow_reuse_address = 1

    def server_bind(self):
        """Override server_bind to store the server name."""
        SocketServer.TCPServer.server_bind(self)
        host, port = self.socket.getsockname()[:2]
        self.server_name = socket.getfqdn(host)
        self.server_port = port

#Handler = SimpleHTTPServer.SimpleHTTPRequestHandler
class MyHTTPRequestHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    def dumpRequestHeaders(self):
        print 'dumpRequestHeaders: raw_requestline=%s \nheaders=\n%s' % (self.raw_requestline,self.headers)

    def copyfile_by_range(self, fin, fout, start, end):
        print "copyfile_by_range: start=%d end=%d" % (start, end)
        READ_BUFFER_SIZE = 4*1024;
        fin.seek(start, os.SEEK_SET)
        if end<0: #代表原始Range请求未指定完整范围，只指定了开始位置
            buf = fin.read(READ_BUFFER_SIZE) #FIXME：健壮性fix，如果读到内容小于size参数？需要判断len(buf)
            if len(buf)!=READ_BUFFER_SIZE:
                print "copyfile_by_range: len(buf)!=READ_BUFFER_SIZE 1 len(buf)=%d" % (len(buf))
            while buf:
                fout.write(buf)
                fout.flush()
                buf = fin.read(READ_BUFFER_SIZE)
                if len(buf)==0:
                    break #??
                if len(buf)!=READ_BUFFER_SIZE:
                    print "copyfile_by_range: len(buf)!=READ_BUFFER_SIZE 2 len(buf)=%d" % (len(buf))
                    fout.write(buf)
                    break
        else:
            bytes_left = end-start+1
            while bytes_left >= READ_BUFFER_SIZE:
                buf = fin.read(READ_BUFFER_SIZE)
                if len(buf)!=READ_BUFFER_SIZE:
                    print "copyfile_by_range: len(buf)!=READ_BUFFER_SIZE 3 len(buf)=%d" % (len(buf))
                fout.write(buf)
                bytes_left = bytes_left - READ_BUFFER_SIZE
            if bytes_left>0:
                buf = fin.read(bytes_left)
                if len(buf)!=bytes_left:
                    print "copyfile_by_range: len(buf)!=bytes_left len(buf)=%d bytes_left=" % (len(buf), bytes_left)
                fout.write(buf)

    def do_GET(self):
        self.dumpRequestHeaders() #用于查看客户端浏览器的User-Agent设置;
        #
        #SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)
        f, range = self.send_head() #原来的send_head这个函数实现有点莫名其妙？
        if f:
            if range:
                #注意，响应头部已经在send_head()里设置完成了，这里只需要调整io读写指针
                self.copyfile_by_range(f, self.wfile, range[0], range[1])
            else:
                self.copyfile(f, self.wfile)
                f.close()

    #重载SimpleHTTPServer.py里的实现，以实现：（1）按修改日期排序（2）正确显示中文
    #TODO：支持更多查询参数？html输出代码美化？
    def list_directory(self, path):
        """Helper to produce a directory listing (absent index.html).
        Return value is either a file object, or None (indicating an
        error).  In either case, the headers are sent, making the
        interface the same as for send_head().
        """
        try:
            list = os.listdir(path)
        except os.error:
            self.send_error(404, "No permission to list directory")
            return None
        #list.sort(key=lambda a: a.lower())
        def compare_by_modtime(x, y):
            stat_x = os.stat(path + "/" + x)
            stat_y = os.stat(path + "/" + y)
            if stat_x.st_mtime < stat_y.st_mtime:
                return -1
            elif stat_x.st_mtime > stat_y.st_mtime:
                return 1
            else:
                return 0
        list.sort(lambda x,y: compare_by_modtime(y,x)) #最近修改的排在前面

        f = StringIO()
        displaypath = cgi.escape(urllib.unquote(self.path))
        f.write('<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">')
        f.write("<html>\n<title>Directory listing for %s</title>\n" % displaypath)
        f.write("<body>\n<h2>Directory listing for %s</h2>\n" % displaypath)
        f.write("<hr>\n<ul>\n")
        for name in list:
            fullname = os.path.join(path, name)
            displayname = linkname = name
            # Append / for directories or @ for symbolic links
            if os.path.isdir(fullname):
                displayname = name + "/"
                linkname = name + "/"
            if os.path.islink(fullname):
                displayname = name + "@"
                # Note: a link to a directory displays with @ and links with /
            f.write('<li><a href="%s">%s</a>|<a href="/playvideo?path=%s">播放</a>\n'
                    % (urllib.quote(linkname), cgi.escape(displayname), urllib.quote( os.path.join(self.path, name))))
                    #self.path是浏览器请求路径，而path是本地文件系统路径
        f.write("</ul>\n<hr>\n</body>\n</html>\n")
        length = f.tell()
        f.seek(0)
        self.send_response(200)
        encoding = "gbk" #sys.getfilesystemencoding()
        self.send_header("Content-Type", "text/html; charset=%s" % encoding)
        self.send_header("Content-Length", str(length))
        self.end_headers()
        return f

    #TODO：支持Range请求，这样可以提供基于HTTP的视频流媒体服务
    def send_head(self):
        """
            overwrite send_head to set Last-Modified & Expires to disable browser cache;
        """
        unquoted_path = urllib.unquote(self.path)
        print "send_head: self.path=%s unquoted_path=%s" % (self.path, unquoted_path)
        PLAYVIDEO_REQUEST = re.compile(r'/playvideo\?path=(.+)$')
        m = PLAYVIDEO_REQUEST.match(unquoted_path)
        if m: #TODO: 重构这里的代码
            video_path = m.group(1)
            print "send_head: video_path=%s" % video_path
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write('<video src="%s" controls></video>' % video_path) #注意，这个地方不需要urllib.quote
            return (None,None)
        path = self.translate_path(self.path)
        f = None
        if os.path.isdir(path):
            if not self.path.endswith('/'):
                # redirect browser - doing basically what apache does
                self.send_response(301)
                self.send_header("Location", self.path + "/")
                self.wfile.flush()
                time.sleep(1)
                self.end_headers()
                return (None,None)
            for index in "index.html", "index.htm":
                index = os.path.join(path, index)
                if os.path.exists(index):
                    path = index
                    break
            else:
                return (self.list_directory(path), None)
        ctype = self.guess_type(path)
        try:
            # Always read in binary mode. Opening files in text mode may cause
            # newline translations, making the actual size of the content
            # transmitted *less* than the content-length!
            f = open(path, 'rb')

            #Get file size:
            f.seek(0, os.SEEK_END)
            filesize = f.tell()
            f.seek(0, os.SEEK_SET)
            #TODO: 检查原始请求是否指定了Range头部
            if self.headers.has_key("Range"):
                range_value = self.headers["Range"]
                print "send_head: range_value=[%s]" % range_value
                #直接使用正则表达式匹配: Range: bytes=100-
                HTTP_RANGE_HEADER = re.compile(r'bytes=([0-9]+)\-(([0-9]+)?)')
                m = re.match(HTTP_RANGE_HEADER, range_value)
                if m:
                    start_str = m.group(1)
                    start = int(start_str)
                    end_str = m.group(2)
                    end = -1
                    if len(end_str)>0:
                        end = int(end_str)
                    #现在可以写Range响应头部了：
                    self.send_response(206, "Partial Content")
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(filesize)) #or str(file_stat[6])
                    self.send_header("Accept-Ranges", "bytes")
                    if end<0:
                        content_range_header_value = "bytes %d-%d/%d" % (start, filesize-1, filesize)
                    else:
                        content_range_header_value = "bytes %d-%d/%d" % (start, end, filesize)
                    self.send_header("Content-Range", content_range_header_value)
                    print "send_head: ok, serve 206 for Range request %s-%s，Content-Range=%s" % (start_str, end_str, content_range_header_value)
                    self.send_header("Connection", "close")
                    self.end_headers()
                    return (f, [start, end])
                else:
                    print "send_head: error! INVALID Range request header!!"
                    self.send_error(400, "Bad Request")
                    self.wfile.flush()
                    self.end_headers()
                    return (None,None)
        except IOError:
            self.send_error(404, "File not found")
            return (None,None)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        file_stat = os.fstat(f.fileno())
        self.send_header("Content-Length", str(file_stat[6]))
        #self.send_header("Last-Modified", self.date_time_string(file_stat.st_mtime))
        self.send_header("Last-Modified", self.date_time_string(time.time()))
        self.send_header("Expires", self.date_time_string(time.time()+5))
        self.send_header("Cache-control", "no-cache, no-store, must-revalidate, max-age=0, proxy-revalidate, no-transform")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        return (f, None)


s = MyThreadingHTTPServer(("", PORT), MyHTTPRequestHandler)
s.serve_forever()