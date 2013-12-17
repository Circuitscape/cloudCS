#!/usr/bin/python
##
## Circuitscape (C) 2013, Brad McRae, Viral B. Shah. and Tanmay Mohapatra 

import os, sys, ast, argparse, ConfigParser, signal, resource
from cloud_cs import run_webgui, stop_webserver

class Daemonizer:
    UMASK = 0
    WORKDIR = "/"
    MAXFD = 1024
    REDIRECT_TO = os.devnull if hasattr(os, "devnull") else "/dev/null"
    
    @staticmethod
    def daemonize():
        try:
            pid = os.fork()
        except OSError, e:
            raise Exception, "%s [%d]" % (e.strerror, e.errno)
        
        if pid != 0:
            os._exit(0)

        os.setsid()
        
        try:
            pid = os.fork()
        except OSError, e:
            raise Exception, "%s [%d]" % (e.strerror, e.errno)
    
        if pid != 0:
            os._exit(0)
        
        os.chdir(Daemonizer.WORKDIR)
        os.umask(Daemonizer.UMASK)
        
        maxfd = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
        if (maxfd == resource.RLIM_INFINITY):
            maxfd = Daemonizer.MAXFD
    
        for fd in range(0, maxfd):
            try:
                os.close(fd)
            except OSError:
                pass

        os.open(Daemonizer.REDIRECT_TO, os.O_RDWR)
        os.dup2(0, 1)
        os.dup2(0, 2)
        return(0)


def sig_handler(sig, frame):
    stop_webserver()

parser = argparse.ArgumentParser(description='Start Circuitscape Cloud')
parser.add_argument('--port', type=int, default=8080)
parser.add_argument('--headless', action='store_true')
parser.add_argument('--daemon', action='store_true')
parser.add_argument('--config', type=str)

args = parser.parse_args()

cfg = ConfigParser.ConfigParser()
if args.config != None:
    cfg.read(args.config)
else:
    cfg.add_section("cloudCS")
    cfg.set("cloudCS", "port", str(args.port))
    cfg.set("cloudCS", "headless", str(args.headless))
    cfg.set("cloudCS", "daemon", str(args.daemon))
    cfg.set("cloudCS", "multiuser", str(False))
    
#cfg.write(sys.stdout)

if cfg.getboolean("cloudCS", "daemon"):
    Daemonizer.daemonize()
    
signal.signal(signal.SIGTERM, sig_handler)
signal.signal(signal.SIGINT, sig_handler)
run_webgui(cfg)
