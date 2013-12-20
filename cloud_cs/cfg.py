
class ServerConfig:
    SERVER_WS_PATH = r'/websocket'
    SERVER_LOGIN_AUTH_PATH = r'/auth/login'
    SERVER_STORAGE_AUTH_PATH = r'/auth/storage'
    
    SERVER_CONFIG = None

    SECTION_DEFAULT = "cloudCS"

    def __init__(self, cfg):
        self.in_cfg = cfg
        self.port = self.cfg_get("port", int, 8080)
        self.multiuser = self.cfg_get("multiuser", bool, False)
        self.host = self.cfg_get("host", str, "localhost")
        self.listen_ip = self.cfg_get("listen_ip", str, "0.0.0.0")
        self.headless = self.cfg_get("headless", bool, False)
        
        self.allowed_users = self.cfg_get("allowed_users", str)
        if self.allowed_users != None:
            self.allowed_users = [line.strip() for line in open(self.allowed_users, 'r')]
            
        self.user_roles = self.cfg_get("user_roles", str)
        if self.user_roles != None:
            user_roles = {}
            for line in open(self.user_roles, 'r'):
                uid, role = line.strip().split()
                user_roles[uid] = role
            self.user_roles = user_roles
            
        self.http_url = "http://" + self.host + ':' + str(self.port) + '/'
        self.ws_url = "ws://" + self.host + ':' + str(self.port) + ServerConfig.SERVER_WS_PATH
        self.storage_auth_redirect_uri = "http://" + self.host + ':' + str(self.port) + ServerConfig.SERVER_STORAGE_AUTH_PATH
    
    def is_user_allowed(self, user):
        if self.allowed_users == None:
            return True
        return (user in self.allowed_users)
    
    def get_user_role(self, user):
        if self.user_roles and (user in self.user_roles):
            return self.user_roles.get(user).split(',')
        return ['user']
    
    def cfg_set(self, nm, val):
        self.in_cfg.set("cloudCS", nm, val)
    
    def cfg_get(self, nm, val_type=str, default=None):
        val = default
        try:
            if val_type == int:
                val = self.in_cfg.getint(ServerConfig.SECTION_DEFAULT, nm)
            elif val_type == bool:
                val = self.in_cfg.getboolean(ServerConfig.SECTION_DEFAULT, nm)
            else:
                val = self.in_cfg.get(ServerConfig.SECTION_DEFAULT, nm)
        except:
            pass
        
        return val
    
            