#!/usr/bin/python3
from http import server
from http.server import SimpleHTTPRequestHandler
import socket
import ssl
import sys


if sys.argv[1:]:
        port = int(sys.argv[1])
else :
        port = 443

server_address = ("", port)

context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain("/root/ssl_file/server.pem","/root/ssl_file/server.key")#自己添加

httpd = server.HTTPServer(server_address,SimpleHTTPRequestHandler)
httpd.socket = context.wrap_socket(httpd.socket, server_side = True)
httpd.serve_forever()