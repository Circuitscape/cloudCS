#!/usr/bin/python
##
## Circuitscape (C) 2013, Brad McRae, Viral B. Shah. and Tanmay Mohapatra 

import sys, ast, argparse
from cloud_cs import run_webgui

parser = argparse.ArgumentParser(description='Start Circuitscape Cloud')
parser.add_argument('--port', type=int)
parser.add_argument('--headless', action='store_false')
parser.add_argument('--multiuser', action='store_true')

args = parser.parse_args()

run_webgui(port=args.port, start_browser=args.headless, multiuser=args.multiuser)
