import time

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
        
        self.allowed_users_file = self.cfg_get("allowed_users", str)
        self.user_roles_file = self.cfg_get("user_roles", str)
        self.last_refresh_time = 0
        self.refresh_user_list()
            
        self.http_url = "http://" + self.host + ':' + str(self.port) + '/'
        self.ws_url = "http://" + self.host + ':' + str(self.port) + ServerConfig.SERVER_WS_PATH
        self.storage_auth_redirect_uri = "http://" + self.host + ':' + str(self.port) + ServerConfig.SERVER_STORAGE_AUTH_PATH
    
    def refresh_user_list(self):
        now = time.time()
        if (now - self.last_refresh_time) < 60*10:
            return
        self.last_refresh_time = now
        if self.allowed_users_file != None:
            with open(self.allowed_users_file, 'r') as f:
                self.allowed_users = [line.strip() for line in f]
            
        if self.user_roles_file != None:
            user_roles = {}
            with open(self.user_roles_file, 'r') as f:
                for line in f:
                    uid, role = line.strip().split()
                    user_roles[uid] = role
                self.user_roles = user_roles
        
    
    def is_user_allowed(self, user):
        self.refresh_user_list()
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
    
            