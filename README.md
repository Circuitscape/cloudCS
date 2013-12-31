cloudCS
=======

- Allows multiple users to use [Circuitscape](https://github.com/Circuitscape/Circuitscape) on a cloud hosted infrastructure.
- Provides a browser based interface for [Circuitscape](https://github.com/Circuitscape/Circuitscape), both on the desktop (standalone mode) and the cloud (multiuser mode).


## Running cloudCS
Use script `bin/cswebgui.py` to bring up the server.
Invoke the script with `-h` parameter for help on available options.

````
usage: cswebgui.py [-h] [--port PORT] [--headless] [--config CONFIG]

Start Circuitscape Cloud

optional arguments:
  -h, --help       show this help message and exit
  --port PORT
  --headless
  --config CONFIG
````

## Standalone Operation

Run `bin/cswebgui.py` to start the server on port 8080 and invoke a browser pointing to it.

Valid options:

- **port**: Port number on which to start the server (default 8080). The server is then accessible over a browser as `http://localhost:port_number/`
- **headless**: The browser is not automatically invoked. You can access the cloudCS HTML interface by pointing your browser at `http://localhost:port_number/`


## Multiuser Operation
Run `bin/cswebgui.py --config cloudCS.cfg` where the file `cloudCS.cfg` is the server configuration.

For more details on available options, refer to the comments in the sample configuration file `cloudCS.cfg.sample`

### Batch Run
- Prepare a local folder with all data files and configuration files within it.
- Files can be organized under sub folders.
- Configuration files must refer to relative paths starting from the folder in which the configuration file itself is located.
- Compress the local root folder into a `zip` archive and upload on to Google Drive.
- Click `Run Batch` in the cloudCS menu and select the uploaded archive.
- The `zip` archive will be downloaded and run on the cloudCS server and results would be archived and uploaded back on to Google Drive.

