"""
    Belasitsa:
    A simple WSGI back end for Mongrel2,
    Inspired by the Battle of Kleidion.
    t@jujit.su 4/23/13
"""
import sys
from uuid import uuid4
from cStringIO import StringIO
import json

import zmq.green as zmq
import gevent


CTX = zmq.Context()


def usage():
    use = '%s: -s send -r recv -a module.app [-w nworkers]'
    print >> sys.stderr, use % sys.argv[0]
    sys.exit(111)


class Mongrel2Connection(object):
    def __init__(self, pull_addr, pub_addr):
        self.sender_id = uuid4().hex

        in_sock = CTX.socket(zmq.PULL)
        in_sock.connect(pull_addr)
        out_sock = CTX.socket(zmq.PUB)
        out_sock.setsockopt(zmq.IDENTITY, self.sender_id)
        out_sock.connect(pub_addr)

        self.in_addr = pull_addr
        self.out_addr = pub_addr
        self.in_sock = in_sock
        self.out_sock = out_sock

    def recv(self):
        return self.in_sock.recv()

    def send(self, uuid, conn_id, msg):
        header = "%s %d:%s," % (uuid, len(str(conn_id)), str(conn_id))
        self.out_sock.send_unicode(header + ' ' + msg)


def make_environ(msg):
    def parse_netstring(ns):
        leng, rest = ns.split(':', 1)
        leng = int(leng)
        assert rest[leng] == ',', "Netstring did not end in ','"
        return rest[:leng], rest[leng+1:]

    path, rest = msg.split(' ', 1)
    headers, rest = parse_netstring(rest)
    headers = json.loads(headers)
    body, _ = parse_netstring(rest)
    if headers['METHOD'] == 'JSON':
        if json.loads(body).get('type') == 'disconnect':
            return None
    path_info = '/'
    query = ''
    uri = headers.get('URI')
    if uri:
        split_path = uri.split('?', 1)
        if len(split_path) == 2:
            path_info, query = split_path
        elif len(split_path) == 1:
            path_info = split_path[0]

    environ = {
            'SCRIPT_NAME': '',
            'PATH_INFO': path_info,
            'QUERY_STRING': query,
            'CONTENT_TYPE': headers.get('content-type', ''),
            'CONTENT_LENGTH': headers.get('content-length', ''),
            'REQUEST_METHOD': headers.get('METHOD'),
            'SERVER_NAME': 'localhost',
            'SERVER_PORT': '80',
            'SERVER_PROTOCOL': headers.get('VERSION'),
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': 'http',
            'wsgi.input': StringIO(body),
            'wsgi.errors': sys.stderr,
            'wsgi.multithread': False,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
    }

    for key, value in headers.items():
        key = 'HTTP_' + key.upper().replace('-', '_')
        if key not in ('HTTP_CONTENT_TYPE', 'HTTP_CONTENT_LENGTH'):
            environ[key] = value

    return environ


def wsgi(app, request):
    """ See PEP-333. """
    body = StringIO()
    headers_set = []
    headers_sent = []

    def write(data):
        if not headers_set:
             raise AssertionError("write() before start_response()")
        elif not headers_sent:
             status, response_headers = headers_sent[:] = headers_set
             body.write('%s %s\r\n' % (environ['SERVER_PROTOCOL'], status))
             for header in response_headers:
                 body.write('%s: %s\r\n' % header)
             body.write('\r\n')

        body.write(data)

    def start_response(status, response_headers, exc_info=None):
        if exc_info:
            try:
                if headers_sent:
                    raise exc_info[0], exc_info[1], exc_info[2]
            finally:
                exc_info = None     # avoid dangling circular ref
        elif headers_set:
            raise AssertionError("Headers already set!")

        headers_set[:] = [status, response_headers]
        return write

    environ = make_environ(request)
    if not environ:
        return None

    result = app(environ, start_response)
    try:
        for data in result:
            if data:
                write(data)
        if not headers_sent:
            write('')
    finally:
        if hasattr(result, 'close'):
            result.close()

    return body.getvalue()


def server(recv, send, app):
    con = Mongrel2Connection(recv, send)
    while True:
        msg_from_mongrel = con.recv()
        sender, conn_id, request = msg_from_mongrel.split(' ', 2)
        response = wsgi(app, request)
        if response:
            con.send(sender, conn_id, response)


if __name__ == '__main__':
    from getopt import getopt
    from getopt import GetoptError
    
    nworkers = 1

    try:
        opts, args = getopt(sys.argv[1:],"s:r:a:w:")
    except GetoptError:
        usage()
    for opt, arg in opts:
        if opt == '-s':
            send = arg
        elif opt == '-r':
            recv = arg
        elif opt == '-w':
            nworkers = int(arg)
        elif opt == '-a':
            module, appname = arg.rsplit('.', 1)
            try:
                imp_app = __import__(module)
            except ImportError, e:
                err_msg = 'could not locate module: %s'
                print >> sys.stderr, err_msg % module
                sys.exit(111)
            try:
                app = imp_app.__dict__[appname]
            except KeyError, e:
                err_msg = 'could not locate app in module: %s'
                print >> sys.stderr, err_msg % appname
                sys.exit(111)
        else:
            assert False, "unhandled option"

    workers = [gevent.spawn(server, recv, send, app)
                for i in xrange(nworkers)]
    gevent.joinall(workers)
