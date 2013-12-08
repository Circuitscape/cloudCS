#!/usr/bin/python
##
## Circuitscape (C) 2013, Brad McRae, Viral B. Shah. and Tanmay Mohapatra 

import sys, ast
from cloud_cs import run_webgui

num_args = len(sys.argv)

if num_args == 1:
    run_webgui()
elif num_args == 2:
    start_browser = ast.literal_eval(sys.argv[1])
    run_webgui(start_browser=start_browser)
elif num_args == 3:
    start_browser = ast.literal_eval(sys.argv[1])
    port = int(sys.argv[2])
    run_webgui(port, start_browser)
