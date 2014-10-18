import httplib
import urlparse
import urllib
import json

def join_paths(*paths):
    request_path = []
    for path in paths:
        if path == '/':
            continue
        elif path.endswith('/'):
            request_path.append(path[:-1])
        elif path.startswith('/'):
            request_path.append(path[1:])
        else:
            request_path.append(path)
    path = u'/'.join(paths)
    if path.endswith('/'):
        path = path[:-1]
    return path

class RestResponse(object):
    def __init__(self, response, content):
        self.response = response
        self.content = content

    @property
    def json(self):
        if not hasattr(self, '_json'):
            self._json = json.loads(self.content)
        return self._json

class RestRequester(object):
    def __init__(self, base_url=None):
        if base_url:
            self.set_base_url(base_url)
        self.h = httplib2.Http(".cache")

    def set_base_url(self, base_url):
        self.base_url = urlparse.urlparse(base_url)
        self.base_scheme, self.base_host, self.base_path, query, fragment = urlparse.urlsplit(base_url)

    def get(self, path, args=None, headers={}):
        return self.request(self.base_scheme, self.base_host,
                join_paths(self.base_path, path), 'GET', args=args,
                headers=headers)

    def get_absolute(self, url, args=None, headers={}):
        scheme, host, path = urlparse.urlsplit(url)
        return self.request(scheme, host, path, 'GET', args=args, headers=headers)

    def post(self, path, args=None, body=None, headers={}):
        return self.request(self.base_scheme, self.base_host,
                join_paths(self.base_path, path), 'POST', args=args,
                body=body, headers=headers)

    def post_absolute(self, path, args=None, body=None, headers={}):
        scheme, host, path = urlparse.urlsplit(url)
        return self.request(scheme, host, path, 'POST', args=args, body=body, headers=headers)

    def put(self, path, args=None, body=None, headers={}):
        return self.request(self.base_scheme, self.base_host,
                join_paths(self.base_path, path), 'PUT', args=args,
                body=body, headers=headers)

    def put_absolute(self, path, args=None, body=None, headers={}):
        scheme, host, path = urlparse.urlsplit(url)
        return self.request(scheme, host, path, 'PUT', args=args, body=body, headers=headers)

    def delete(self, path, args=None, headers={}):
        return self.request(self.base_scheme, self.base_host,
                join_paths(self.base_path, path), 'DELETE', args=args,
                headers=headers)

    def delete_absolute(self, url, args=None, headers={}):
        scheme, host, path = urlparse.urlsplit(url)
        return self.request(scheme, host, path, 'DELETE', args=args, headers=headers)

    def head(self, path, args=None, headers={}):
        return self.request(self.base_scheme, self.base_host,
                join_paths(self.base_path, path), 'GET', args=args,
                headers=headers)

    def head_absolute(self, url, args=None, headers={}):
        scheme, host, path = urlparse.urlsplit(url)
        return self.request(scheme, host, path, 'HEAD', args=args, headers=headers)

    def request(self, scheme, host, path, method='GET', args=None, body=None, headers={}):
        headers['User-Agent']= 'Basic Agent'

        if args:
            if method == 'GET':
                path += u'?' + urllib.urlencode(args)
            elif method == 'PUT' or method == 'POST':
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                body = urllib.urlencode(args, True)

        return RestResponse(*self.h.request(u'%s://%s%s' % (scheme, host, path),
                method.upper(), body=body, headers=headers))