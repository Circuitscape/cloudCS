import traceback, tempfile

from circuitscape import __version__ as cs_version
from circuitscape import __author__ as cs_author

import tornado.web

class PageHandlerBase(tornado.web.RequestHandler):
    def generic_get_error_html(self, status_code, **kwargs):
        kwargs.update({
                  'version': cs_version,
                  'author': cs_author,                  
                  'status_code': status_code,
        })
        
        if self.settings.get("debug") and "exc_info" in kwargs:
            exc_info = kwargs["exc_info"]
            trace_info = ''.join(["%s<br/>" % line for line in traceback.format_exception(*exc_info)])
            request_info = ''.join(["<strong>%s</strong>: %s<br/>" % (k, self.request.__dict__[k] ) for k in self.request.__dict__.keys()])
            error = exc_info[1]
            
            kwargs['message'] = "<br/><br/>".join([kwargs['message'], "Error: " + error, "Request Info: " + request_info, "Trace: " + trace_info])
            
        return self.render_string("cs_error.html", **kwargs)

class ErrorHandler(tornado.web.ErrorHandler, PageHandlerBase): 
    def prepare(self): 
        raise tornado.web.HTTPError(self._status_code) 


class Utils:
    temp_files_root = None
    
    @staticmethod
    def mkdtemp(suffix="", prefix=""):
        return tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=Utils.temp_files_root)
    
