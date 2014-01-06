import os, StringIO, time, shutil, logging
from multiprocessing import Process, Value

from circuitscape.compute import Compute
from circuitscape.cfg import CSConfig
from circuitscape.io import CSIO
from circuitscape import __file__ as cs_pkg_file

from common import Utils, AsyncRunner
from cloudstore import GoogleDriveStore


class CircuitscapeRunner(AsyncRunner):
    MAX_PARALLEL = 20
    
    def __init__(self, wslogger, wsmsg, method, client_ctx, *args):
        self.logger.debug("Server currently running " + str(self.process_count) + " processes.")
         
        if self.process_count >= CircuitscapeRunner.MAX_PARALLEL:
            raise "Server Overloaded"        
        
        self.sess = wslogger.dest.sess
        self.run_log = wslogger.tee_dest.name if (None != wslogger.tee_dest) else None
        super(CircuitscapeRunner, self).__init__(wslogger, wsmsg, method, client_ctx, *args)
    
    def completed(self):
        self.wslogger.flush()
        self.sess.task = None
        self.logger.debug("task completed for session " + self.sess.sess_id)
        if self.run_log:
            Utils.stash_last_run_log("", self.sess.user_id(), self.run_log)
            self.logger.debug("stashed run log " + self.run_log)
    
    def srvr_log(self, level, msg):
        self.logger.log(level, str(self.sess.sess_id) + " - " + str(msg))
    
    def attach(self, dest):
        old_sess_id = self.sess.sess_id
        self.wslogger.attach(dest)
        self.sess = dest.sess
        self.wsmsg.handler = dest
        self.logger.debug("task re-attached to session " + self.sess.sess_id + " from old session " + old_sess_id)
        
    def detach(self):
        wslogger = self.wslogger
        if (None != wslogger) and (None != wslogger.dest):
            wslogger.detach()
        self.wsmsg.handler = None
        self.logger.debug("task detached from session " + self.sess.sess_id)
    
    #TODO: The hardcoded values for role limits need to be configurable
    @staticmethod
    def check_role_limits(roles, cfg, qlogger):
        qlogger.clnt_log("Your roles: " + str(roles))
        if ("admin" in roles) or ("standalone" in roles):
            return (True, None)
        
        try:
            # check max parallel
            qlogger.clnt_log("Parallelization requested: " + str(cfg.parallelize))
            if cfg.parallelize:
                qlogger.clnt_log("Parallel processes requested: " + (str(cfg.max_parallel) if (cfg.max_parallel > 0) else "maximum"))
                if cfg.max_parallel == 0:
                    cfg.max_parallel = CircuitscapeRunner.MAX_PARALLEL
                else:
                    return (False, "Your profile is restricted to a maximum of " + str(CircuitscapeRunner.MAX_PARALLEL) + " parallel processors.")
            
            # check for cumulative maps
            qlogger.clnt_log("Output maps required for - voltage: " + str(cfg.write_volt_maps) + ", current: " + str(cfg.write_cur_maps) + ", cumulative only: " + str(cfg.write_cum_cur_map_only))
            if cfg.write_volt_maps or (cfg.write_cur_maps and (not cfg.write_cum_cur_map_only)):
                return (False, "Your profile is restricted to create only cumulative current maps.")
            
            # check problem size
            prob_sz = CSIO.problem_size(cfg.data_type, cfg.habitat_file)
            qlogger.clnt_log("Habitat size: " + str(prob_sz))
            if prob_sz > 24000000:
                return (False, "Your profile is restricted for habitat sizes of 24m nodes only.")
        except Exception as e:
            return (False, "Unknown error verifying limits. (" + str(e) + "). Please check your input files.")
        
        return (True, None)
    
    @staticmethod
    def upload_results(qlogger, output_folder, output_zip_name, work_dir, cloud_folder_id, store, extract_folder_id=False):
        qlogger.flush()
        qlogger.clnt_log("Compressing results for upload...")
        
        # copy the tee log to output folder
        run_log_file = os.path.join(work_dir, "run.log")
        shutil.copyfile(run_log_file, os.path.join(output_folder, "run.log"))
        
        Utils.compress_folder(output_folder, output_zip_name)
        
        for attempt in range(1,11):
            qlogger.clnt_log("Uploading results to cloud store...")
            qlogger.flush()
            if None == store.copy_to_remote(cloud_folder_id, output_zip_name, mime_type='application/zip', extract_folder_id=extract_folder_id):
                qlogger.clnt_log("Error uploading output.zip. attempt " + str(attempt) + " of 10")
                qlogger.srvr_log(logging.WARNING, "Error uploading output.zip. attempt " + str(attempt) + " of 10")
                time.sleep(5*attempt)
            else:
                break
        
        qlogger.clnt_log("Uploaded results to cloud store")
        Utils.rmdir(output_folder, True)
        os.remove(output_zip_name)
        #os.remove(run_log_file)


    @staticmethod
    def run_job(qlogger, msg_type, roles, msg_data, work_dir, storage_creds, store_in_cloud):
        qlogger.srvr_log(logging.INFO, "beginning run_job")
        solver_failed = True
        output_cloud_folder = None
        output_folder = None
        cfg = CSConfig()
        store = GoogleDriveStore(storage_creds) if (None != storage_creds) else None
        
        for key in msg_data.keys():
            val = msg_data[key]
            if store_in_cloud and (key in CSConfig.FILE_PATH_PROPS) and (val != None):
                # if val is gdrive location, translate it to local drive
                if val.startswith("gdrive://"):
                    if key == 'output_file':
                        # store the output gdrive folder
                        qlogger.clnt_log("Preparing cloud store output folder: " + val)
                        output_cloud_folder = val
                        output_folder = os.path.join(work_dir, 'output')
                        if not os.path.exists(output_folder):
                            os.mkdir(output_folder)
                        else:
                            Utils.rmdir(output_folder, True)
                        val = os.path.join(output_folder, 'results.out')
                    else:
                        # copy the file locally
                        qlogger.clnt_log("Reading from cloud store: " + val)
                        val = store.copy_to_local(val, work_dir)
            cfg.__setattr__(key, val)
        
        qlogger.clnt_log("Verifying configuration...")
        (all_options_valid, message) = cfg.check()
        
        if all_options_valid:
            qlogger.clnt_log("Verifying profile limits...")
            (all_options_valid, message) = CircuitscapeRunner.check_role_limits(roles, cfg, qlogger)
            
        if not all_options_valid:
            qlogger.send_error_msg(message)
        else:
            # In cloud mode, this would be a temporary directory
            outdir, _out_file = os.path.split(cfg.output_file)
            
            try:
                qlogger.clnt_log("Storing final configuration...")
                configFile = os.path.join(outdir, 'circuitscape.ini')
                cfg.write(configFile)
    
                cs = Compute(configFile, qlogger)
                result, solver_failed = cs.compute()
                qlogger.clnt_log("Result: \n" + str(result))
            except Exception as e:
                message = str(e)
                qlogger.send_error_msg(message)

        success = not solver_failed
        
        if success and store_in_cloud:
            output_folder_zip = os.path.join(work_dir, 'output.zip')
            CircuitscapeRunner.upload_results(qlogger, output_folder, output_folder_zip, work_dir, output_cloud_folder, store, extract_folder_id=False)
        
        qlogger.srvr_log(logging.INFO, "end run_job")
        qlogger.send_result_msg(msg_type, {'complete': True, 'success': success})
    
    @staticmethod
    def run_verify(qlogger, msg_type, roles):
        qlogger.srvr_log(logging.INFO, "beginning run_verify")
        outdir = None
        cwd = os.getcwd()
        strio = StringIO.StringIO()
        try:
            root_path = os.path.dirname(cs_pkg_file)
            outdir = Utils.mkdtemp(prefix="verify_")
            if os.path.exists(root_path):
                root_path = os.path.split(root_path)[0]
                os.chdir(root_path)     # otherwise we are running inside a packaged folder and resources are availale at cwd
            from circuitscape.verify import cs_verifyall
            testResult = cs_verifyall(out_path=outdir, ext_logger=qlogger, stream=strio)
            testsPassed = testResult.wasSuccessful()
        except Exception as e:
            qlogger.clnt_log("Unexpected error during verify.")
            qlogger.srvr_log(logging.WARNING, "Exception during verify: " + str(e))
            testsPassed = False
        finally:
            os.chdir(cwd)
            Utils.rmdir(outdir)

        qlogger.clnt_log(strio.getvalue())
        strio.close()
        qlogger.srvr_log(logging.INFO, "end run_verify")
        qlogger.send_result_msg(msg_type, {'complete': True, 'success': testsPassed})

    @staticmethod
    def _run_compute(configFile, qlogger, prefix, res):
        qlogger.set_prefix(prefix)
        cs = Compute(configFile, qlogger)
        result, solver_failed = cs.compute()
        qlogger.clnt_log("Result: \n" + str(result))
        res.value = -1 if solver_failed else 0
    

    @staticmethod
    def run_batch(qlogger, msg_type, roles, msg_data, work_dir, storage_creds, store_in_cloud):
        qlogger.srvr_log(logging.INFO, "beginning run_batch")
        cwd = os.getcwd()
        store = GoogleDriveStore(storage_creds) if (None != storage_creds) else None
        
        if store_in_cloud:
            batch_zip = msg_data
            batch_zip_name = os.path.splitext(store.to_file_name(batch_zip))[0]  + '_output.zip'
            qlogger.clnt_log("Reading from cloud store: " + batch_zip)
            batch_folder = Utils.mkdtemp(prefix="batch_")
            batch_zip = store.copy_to_local(batch_zip, work_dir)
            Utils.uncompress_folder(batch_folder, batch_zip)
            os.remove(batch_zip)
            
            output_folder_zip = os.path.join(work_dir, batch_zip_name)
        else:
            batch_folder = msg_data
            qlogger.clnt_log("Running batch with all configurations (.ini files) under folder: " + batch_folder)
            
        
        output_root_folder = Utils.mkdtemp_if_exists(prefix="output", dir=batch_folder)

        if store_in_cloud:
            qlogger.clnt_log("Outputs would be uploaded to your cloud store as " + batch_zip_name)
        else:
            qlogger.clnt_log("Outputs would be stored under folder: " + output_root_folder)
        
        num_success = 0
        num_failed = 0
        
        # collect all configuration names
        config_files = []
        for root, _dirs, files in os.walk(batch_folder):
            for file_name in files:
                if not file_name.endswith(".ini"):
                    continue
                config_files.append(os.path.join(root, file_name))
        
        num_configs = len(config_files)
        qlogger.clnt_log("Found " + str(num_configs) + " configuration files.")
        parallelize = True if (num_configs > CircuitscapeRunner.MAX_PARALLEL) else False
        
        batch_success = False
        if parallelize:
            pool = []
            results = []
            
        try:
            for config_file in config_files:
                root, file_name = os.path.split(config_file)
                qlogger.clnt_log("Loading configuration: " + config_file)
         
                cfg = CSConfig(config_file)
         
                os.chdir(root)       
                qlogger.clnt_log("Verifying configuration...")
                
                if parallelize: # switch off parallization of each task if we are parallelizing batch
                    cfg.parallelize = False
                    
                (all_options_valid, message) = cfg.check()
                #qlogger.clnt_log("Verified configuration with result: " + str(all_options_valid))
                
                if all_options_valid:
                    #qlogger.clnt_log("Verifying all paths are relative...")
                    all_options_valid = cfg.are_all_paths_relative();
                    if not all_options_valid:
                        message = "All file paths in configuration must be relative to location of configuration file."
                
                #qlogger.clnt_log("Verified configuration with result: " + str(all_options_valid))
                if all_options_valid:
                    qlogger.clnt_log("Verifying profile limits...")
                    (all_options_valid, message) = CircuitscapeRunner.check_role_limits(roles, cfg, qlogger)
                    
                if not all_options_valid:
                    qlogger.send_error_msg(message)
                    num_failed += 1
                else:
                    solver_failed = True
                    cfgname = os.path.splitext(file_name)[0]
                    output_folder = os.path.join(output_root_folder, cfgname)
                    os.mkdir(output_folder)
                    cfg.output_file = os.path.join(output_folder, os.path.basename(cfg.output_file))
                    
                    outdir, _out_file = os.path.split(cfg.output_file)
                    
                    try:
                        qlogger.clnt_log("Storing final configuration...")
                        configFile = os.path.join(outdir, 'circuitscape.ini')
                        cfg.write(configFile)
            
                        if parallelize:
                            if len(pool) >= CircuitscapeRunner.MAX_PARALLEL:
                                p = pool.pop()
                                p.join()
                                result = results.pop()
                                if result.value == 0:
                                    num_success += 1
                                else:
                                    num_failed += 1
                                    
                            result = Value('i', -1)
                            p = Process(target=CircuitscapeRunner._run_compute, args=(configFile, qlogger, cfgname + ' => ', result))
                            pool.append(p)
                            results.append(result)
                            p.start()
                        else:
                            cs = Compute(configFile, qlogger)
                            result, solver_failed = cs.compute()
                            qlogger.clnt_log("Result: \n" + str(result))
                    except Exception as e:
                        message = str(e)
                        qlogger.send_error_msg(message)
                    
                    if not parallelize:
                        if solver_failed:
                            num_failed += 1
                        else:
                            num_success += 1

            if parallelize:
                qlogger.srvr_log(logging.DEBUG, "waiting for pracesses len=" + str(len(pool)))
                for idx in range(0, len(pool)):
                    pool[idx].join()
                    if results[idx].value == 0:
                        num_success += 1
                    else:
                        num_failed += 1
                
            qlogger.srvr_log(logging.DEBUG, "Batch run done for " + str(len(config_files)) + " configuration files. Success: " + str(num_success) + ". Failures: " + str(num_failed))    
            qlogger.clnt_log("Batch run done for " + str(len(config_files)) + " configuration files. Success: " + str(num_success) + ". Failures: " + str(num_failed))
            
            if num_success > 0:
                if store_in_cloud:
                    CircuitscapeRunner.upload_results(qlogger, output_root_folder, output_folder_zip, work_dir, msg_data, store, extract_folder_id=True)
                else:
                    qlogger.clnt_log("Outputs under folder: " + output_root_folder)
                batch_success = True
        except Exception as e:
            qlogger.clnt_log("Unexpected error during batch run.")
            qlogger.srvr_log(logging.WARNING, "Exception during batch run: " + str(e))
        finally:
            os.chdir(cwd)
            if store_in_cloud:
                try:
                    Utils.rmdir(batch_folder)
                    if os.path.exists(output_folder_zip):
                        os.remove(output_folder_zip)
                except:
                    qlogger.srvr_log(logging.ERROR, "Could not clear temporary files.")
        
        qlogger.srvr_log(logging.INFO, "end run_batch")
        qlogger.send_result_msg(msg_type, {'complete': True, 'success': batch_success})
