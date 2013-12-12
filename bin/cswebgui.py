#!/usr/bin/python
##
## Circuitscape (C) 2013, Brad McRae, Viral B. Shah. and Tanmay Mohapatra 

import sys, ast, argparse, ConfigParser, signal
from cloud_cs import run_webgui, stop_webserver

parser = argparse.ArgumentParser(description='Start Circuitscape Cloud')
parser.add_argument('--port', type=int, default=8080)
parser.add_argument('--headless', action='store_true')
parser.add_argument('--config', type=str)

args = parser.parse_args()

cfg = ConfigParser.ConfigParser()
if args.config != None:
    cfg.read(args.config)
else:
    cfg.add_section("cloudCS")
    cfg.set("cloudCS", "port", str(args.port))
    cfg.set("cloudCS", "headless", str(args.headless))
    cfg.set("cloudCS", "multiuser", str(False))
    
#cfg.write(sys.stdout)

def sig_handler(sig, frame):
    stop_webserver()
    
signal.signal(signal.SIGTERM, sig_handler)
signal.signal(signal.SIGINT, sig_handler)
run_webgui(cfg)
