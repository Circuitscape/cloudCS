import tornado.web
import tornado.auth
import hashlib, time, logging

logger = logging.getLogger('cloudCS')

class Session:
    COOKIE_NAME = "cloudcs_sess"
    SALT = "couldcs"  #TODO: this should be read from a configuration file at runtime
        
    def auth_valid(self, req):
        logger.debug("authenticated " + self.user_id())
        req.set_secure_cookie(Session.COOKIE_NAME, self.sess_id, 1)
        req.redirect('/')

    @classmethod
    def validated_user_id(cls, req):
        return cls.get_session(cls.extract_session_id(req)).user_id()
    
    @classmethod
    def validated_user_name(cls, req):
        return cls.get_session(cls.extract_session_id(req)).user_name()
    
    @classmethod
    def extract_session_id(cls, req):
        return req.get_secure_cookie(Session.COOKIE_NAME)
        
    @classmethod
    def validate(cls, req):
        logger.debug("validating request")
        valid = False
        try:
            sess_id = cls.extract_session_id(req)
            valid = cls.validate_sess_id(sess_id)
        except Exception as e:
            logger.exception("Exception in validating")
        finally:
            if not valid:
                logger.debug("redirecting request for authentication")
                req.redirect('/auth')
                return False
            return True

    @classmethod
    def validate_sess_id(cls, sess_id):
        logger.debug('validating sess_id ' + sess_id)
        sess = cls.get_session(sess_id) if (sess_id != None) else None
        logger.debug('sess = ' + str(sess) + " for sess_id " + sess_id)
        return (sess != None)

        


class AuthHandlerBase(tornado.web.RequestHandler):
    def _on_auth(self, user):
        if not user:
            raise tornado.web.HTTPError(500, "Google auth failed")
        
        logger.debug("got google user: " + str(user))
        SessionInMemory(user).auth_valid(self)
        
    
class GoogleHandler(AuthHandlerBase, tornado.auth.GoogleMixin):
    @tornado.web.asynchronous
    def get(self):
        logger.debug("google auth invoked")
        if self.get_argument("openid.mode", None):
            self.get_authenticated_user(self.async_callback(self._on_auth))
            return
        self.authenticate_redirect()


class SessionInMemory(Session):
    SESS_STORE = {}
    
    def __init__(self, user):
        self.user = user
        self.uid = user['email']
        self.creation_time = time.time()
        self.sess_id = hashlib.sha1('_'.join([self.uid, Session.SALT, str(self.creation_time)])).hexdigest()
        SessionInMemory.SESS_STORE[self.sess_id] = self
        logger.debug("created session for " + self.uid + " with key " + self.sess_id)
    
    def user_id(self):
        return self.uid
    
    def user_name(self):
        return self.user['name']
    
        
    @classmethod
    def is_valid(cls, sess_id):
        return (sess_id in SessionInMemory.SESS_STORE.keys())

    @classmethod
    def get_session(cls, sess_id):
        sess = None
        if SessionInMemory.is_valid(sess_id):
            sess = SessionInMemory.SESS_STORE[sess_id]
            logger.debug("got sess " + str(sess))
        else:
            logger.error("session id " + str(sess_id) + " not found")            
        return sess

    @classmethod
    def logout(cls, sess_id):
        if sess_id:
            logger.debug("logging out " + str(sess_id))
            del SessionInMemory.SESS_STORE[sess_id]

