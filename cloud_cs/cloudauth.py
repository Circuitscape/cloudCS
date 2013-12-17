import logging

import tornado.web
import tornado.auth

from common import PageHandlerBase
from session import SessionInMemory as Session

logger = logging.getLogger('cloudCS')


class AuthHandlerBase(PageHandlerBase):
    def _on_auth(self, user):
        if not user:
            raise tornado.web.HTTPError(500, "Google auth failed")
        
        logger.debug("got google user: " + str(user))
        Session(user).auth_valid(self)

    def get_error_html(self, status_code, **kwargs):
        return self.generic_get_error_html(status_code, message="Could not authenticate you.");
        
    
class GoogleHandler(AuthHandlerBase, tornado.auth.GoogleMixin):
    @tornado.web.asynchronous
    def get(self):
        logger.debug("google auth invoked")
        if self.get_argument("openid.mode", None):
            self.get_authenticated_user(self.async_callback(self._on_auth))
            return
        self.authenticate_redirect()
