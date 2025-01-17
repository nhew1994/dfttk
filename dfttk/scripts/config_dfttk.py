# -*- coding: utf-8 -*-
#
#Configure script for dfttk

import warnings
import subprocess
from dfttk.scripts.run_dfttk import get_abspath, creat_folders
from pymatgen.io.vasp.inputs import PotcarSingle, Potcar
from pymatgen.ext.matproj import MPRester
from dfttk.utils import recursive_glob
from monty.serialization import loadfn, dumpfn
from monty.os.path import which
import getpass
import shutil
import math
import os
import re
from pathlib import Path

def get_machines(nodes=1, ppn=16, user_machines=None):
    if user_machines is not None:
        machines = loadfn(user_machines)
    else:
        machines = {"cori-hsw":{"constraint": "haswell", "queue": "regular",
                "_fw_q_type": "SLURM",
                "account": "m891",
                "pre_rocket": "module load vasp/5.4.4-hsw",
                "post_rocket": "",
                "mem": "64gb",
                "vasp_cmd": "srun -n "+str(int(nodes)*int(ppn))+" --cpu_bind=cores vasp_std"}
          ,"cori-knl":{"constraint": "knl,quad,cache", "queue": "regular",
                "_fw_q_type": "SLURM",
                "account": "m891",
                "pre_rocket": "module load vasp/5.4.4-knl",
                "mem": "64gb",
                "post_rocket": "",
                "vasp_cmd": "srun -n "+str(int(nodes)*int(ppn))+" --cpu_bind=cores vasp_std"}
          ,"bridges2":{"queue": "RM",
                "_fw_q_type": "SLURM",
                "account": "dmr170016p",
                "pre_rocket": "module load intel cuda intelmpi/20.4-intel20.4",
                "post_rocket": "",
                "vasp_cmd": "mpirun -np "+str(nodes*ppn)+" /opt/packages/VASP/VASP5/INTEL/vasp_std"}
          ,"stampede2":{"queue": "normal",
                "_fw_q_type": "SLURM",
                "account": "TG-DMR140063",
                "pre_rocket": "module load vasp/5.4.4",
                "post_rocket": "",
                "vasp_cmd": "ibrun -np "+str(nodes*ppn)+" vasp_std"}
          ,"aci-vasp5":{"queue": "open", #aci-b is obsolete, however, this could be a template  PBS
                "_fw_q_type": "PBS",
                "account": "open",
                "pre_rocket": "module load intel/19.1.2\n"+\
                              "module load impi/2019.8\n"+\
                              "module use /gpfs/group/RISE/sw7/modules\n"+\
                              "module load vasp\n"+\
                              "export UCX_TLS=all",
                "post_rocket": "",
                "vasp_cmd": "mpirun vasp_std"}
          ,"aci-vasp6":{"queue": "open", #aci-b is obsolete, however, this could be a template  PBS
                "_fw_q_type": "PBS",
                "account": "open",
                "pre_rocket": "module load intel/19.1.2\n"+\
                              "module load impi/2019.8\n"+\
                              "module use /gpfs/group/RISE/sw7/modules\n"+\
                              "module load vasp/vasp-6.2.0\n"+\
                              "export UCX_TLS=all",
                "post_rocket": "",
                "vasp_cmd": "mpirun vasp_std"}
          ,"aci-roar":{"queue": "open",
                "_fw_q_type": "PBS",
                "account": "open",
                "pre_rocket": "#",
                "post_rocket": "",
                "_fw_template_file": os.path.join(".", "config", "PBS_template_custom.txt"),
                "vasp_cmd": "mpirun vasp_std"}
            }
        #dumpfn(machines, "machines.yaml", default_flow_style=False, indent=4)
        dumpfn(machines, "machines.yaml")
    return machines

def replace_file(filename, old_str, new_str):
    """
    Replace the old_str with new_str in filename

    Parameter
        filename: str (filename)
            The file name of the file to be replace
        old_str: str
            The string need to be replaced
        new_str: str
            The new string
    Return
        None, but the file (name with filename) is updated
    """
    with open(filename, "r") as fid:
        lines = fid.readlines()
    with open(filename, "w+") as fid:
        for line in lines:
            a = re.sub(old_str, new_str, line)
            fid.writelines(a)

def default_path():
    #Get the install path of dfttk
    import dfttk
    return os.path.dirname(dfttk.__file__)

def add_path_var(force_override=True, **kwarg):
    """
    Add path var to ~/.bashrc

    If the key of kwarg exists in ~/.bashrc, it will update it,
    if not exists, it will add "export key=kwarg[key]"
    Note: it will backup the original ~/.bashrc to ~/.bashrc.dfttk.bak
    """
    def var_is_exist(var):
        var_expand = os.path.expandvars("$"+var)
        if var_expand == "$" + var:
            return False
        else:
            return True
    #Path.home() is better that os.environ["HOME"]
    #in fact, for Windows, no HOME env defined by default
    homepath = str(Path.home()) #compatible for windows and Linux
    bashrc = os.path.join(homepath,".bashrc")
    if os.path.exists (bashrc):
        shutil.copyfile(bashrc, os.path.join(homepath,".bashrc.dfttk.bak"))  #backup the .bashrc file
    cshrc = os.path.join(homepath, ".cshrc")
    if os.path.exists (cshrc):
        shutil.copyfile(cshrc, os.path.join(homepath,".cshrc.dfttk.bak"))  #backup the .bashrc file
    tcshrc = os.path.join(homepath, ".tcshrc")
    if os.path.exists (tcshrc):
        shutil.copyfile(tcshrc, os.path.join(homepath,".tcshrc.dfttk.bak"))  #backup the .bashrc file
    zshrc = os.path.join(homepath, ".zshrc")
    if os.path.exists (zshrc):
        shutil.copyfile(tcshrc, os.path.join(homepath,".zshrc.dfttk.bak"))  #backup the .bashrc file

    line = "\n#######The following vars are generated by dfttk###########\n"
    tline = "\n#######The following vars are generated by dfttk###########\n"
    for key in kwarg:
        try:
            key = str(key)
        except Exception as e:
            raise e
        if key.startswith("$"):
            key = key[1:]
        if force_override:
            line += "export {key}={value}\n".format(key=key, value=kwarg[key])
            tline += "setenv {key} {value}\n".format(key=key, value=kwarg[key])
        else:
            if var_is_exist(key):
                line += "export {key}=${key}:{value}\n".format(key=key, value=kwarg[key])
                tline += "setenv {key} ${key}:{value}\n".format(key=key, value=kwarg[key])
            else:
                line += "export {key}={value}\n".format(key=key, value=kwarg[key])
                tline += "setenv {key} {value}\n".format(key=key, value=kwarg[key])
    line += "########Above vars are generated by dfttk################\n"
    tline += "########Above vars are generated by dfttk################\n"
    _line = line.split("\n")
    _tline = tline.split("\n")
    for fn in [bashrc, zshrc]:
        if os.path.exists (fn):
            with open(fn, "r") as fid:
                lines = fid.readlines()
                lines=[l.strip() for l in lines]
            if not set(_line).issubset(lines):
                with open(fn, "a+") as fid:
                    fid.write(line)
        else:
            with open(fn, "w") as fid:
                fid.write(line)

    for fn in [cshrc, tcshrc]:
        if os.path.exists (fn):
            with open(fn, "r") as fid:
                lines = fid.readlines()
                lines=[l.strip() for l in lines]
            if not set(_tline).issubset(lines):
                with open(fn, "a+") as fid:
                    fid.write(tline)
        else:
            with open(fn, "w") as fid:
                fid.write(line)


def get_shortest_path(path_list):
    """
    Return the shortest path (the uppest path)
    (Used for find the uppest path for the files with the same filename)

    Parameter
        path_list: list[path-like str], e.g. ["./db.json", "./test/db.json", "./config/db.json"]
    Return
        return the shortest path, e.g. "./db.json"
    """
    path_len = [len(path_i) for path_i in path_list]
    return path_list[path_len.index(min(path_len))]

def get_config_file(config_folder=".", queue_script="vaspjob.pbs"):
    """
    Get the file name of the config file in config_folder and its sub-folders

    Parameter
        config_folder: str (path like)
            The folder containing the config file or containing config file in its sub-folder
        queue_script: str (filename like)
            The filename of the queue script
    Return
        config_file: dict
            The dict of the filename(key) and corresponding path(value).
            If the config file is not in config_folder, store None.
            If more than one file (the same filename), it will store the uppest file [Ref. get_shortest_path]
    """
    config_file = {}
    required_file = ["db.json", "my_launchpad.yaml"]
    option_file = ["FW_config.yaml", "my_fworker.yaml", "my_qadapter.yaml", queue_script]
    files = required_file + option_file
    for file in files:
        file_list = recursive_glob(config_folder, file)
        if len(file_list) == 0:
            if file in required_file:
                raise FileNotFoundError("{} file is required for configuration of dfttk.".format(file))
            else:
                warnings.warn("{} file does not exist, the default setting will be used.".format(file))
                config_file[file] = None
        else:
            config_file[file] = get_abspath(get_shortest_path(file_list))
    return config_file

def parase_pbs_script(filename = "vaspjob.pbs", vasp_cmd_flag="vasp_std"):
    """
    Parse pbs script for config usage

    Parameter
        filename: str (filename-like)
            The filename of the pbs script
        vasp_cmd_flag: str
            The flag to distinguish vasp_cmd with other commands
    Return
        param_dict: dict
            The dict of parameters. It support vasp_cmd, pre_rocket, post_rocket
    """
    s = {"-q": "queue", "-A": "account", "-N": "job_name", "-V": "env",
         "-G": "group_name"}
    param_dict = {"post_rocket": [], "pre_rocket": []}
    flag_post = False

    with open(filename, "r") as fid:
        for eachline in fid:
            eachline = eachline.strip()
            if eachline.startswith("#PBS"):
                line_list = re.split("\s+", eachline)
                if line_list[1] == "-l":
                    if line_list[2].startswith("walltime"):
                        # walltime
                        param_dict["walltime"] = line_list[2].split("=")[1]
                    else:
                        for item in line_list[2].split(":"):
                            key = item.split("=")[0]
                            # nodes, ppn, pmem
                            value = item.split("=")[1]
                            param_dict[key] = value
                else:
                    if line_list[1] in s:
                        param_dict[s[line_list[1]]] = line_list[2]
            elif vasp_cmd_flag in eachline:
                param_dict["vasp_cmd"] = eachline
                flag_post = True
            elif eachline.startswith("cd $") or eachline.startswith("#") or (not eachline):
                #The cd $PBS_O_WORKDIR, or comments(#) or empty
                pass
            else:
                if flag_post:
                    param_dict["post_rocket"].append(eachline)
                else:
                    param_dict["pre_rocket"].append(eachline)
    for param in param_dict:
        try:
            len_param = len(param_dict[param])
            if len_param == 0:
                param_dict[param] = None
            elif len_param == 1:
                param_dict[param] = param_dict[param][0]
        except Exception as e:
            pass
    return param_dict

def parse_queue_script(template="vaspjob.pbs", queue_type="pbs", vasp_cmd_flag="vasp_std"):
    """
    Parse the queue script. Currently only pbs is supported

    Parameter
        template: str (filename-like)
            The filename of the queue script. Default: vaspjob.pbs
        queue_type: str
            The type of queue system. Default: pbs
        vasp_cmd_flag: str
            The flag to distinguish vasp_cmd to other commands in the queue script. Default: vasp_std
    Return
    """
    param_dict = {}
    if queue_type == "pbs":
        param_dict = parase_pbs_script(filename=template, vasp_cmd_flag=vasp_cmd_flag)
    else:
        raise ValueError("Only PBS is supported now. Other system will coming soon...")
    return param_dict

def parse_psp_name(psp_name):
    """
    Parse the name of vasp's psp

    Parameter
        psp_name: str
            The name of vasp's psp, e.g. GGA, LDA, potpaw_LDA
    Return
        psp_name_norm: str
            The normalized psp name
    """
    psp_name = psp_name.upper()
    psp_name_list = re.split(r'\.|\_|\-|\=|\+|\*|\s',psp_name)
    flag_us = False
    for psp_name_i in psp_name_list:
        if "US" in psp_name_i:
            flag_us = True
            break
    if "LDA" in psp_name_list:
        if "52" in psp_name_list:
            psp_name_norm = "POT_LDA_PAW_52"
        elif "54" in psp_name_list:
            psp_name_norm = "POT_LDA_PAW_54"
        elif flag_us:
            psp_name_norm = "POT_LDA_US"
        else:
            psp_name_norm = "POT_LDA_PAW"
    elif "PBE" in psp_name_list:
        if "52" in psp_name_list:
            psp_name_norm = "POT_GGA_PAW_PBE_52"
        elif "54" in psp_name_list:
            psp_name_norm = "POT_GGA_PAW_PBE_54"
        else:
            psp_name_norm = "POT_GGA_PAW_PBE"
    elif "GGA" in psp_name_list:
        if flag_us:
            psp_name_norm = "POT_GGA_US_PW91"
        else:
            psp_name_norm = "POT_GGA_PAW_PW91"
    else:
        warnings.warn("{} is not a proper name of vasp's pseudopotential, please ref \
            https://github.com/PhasesResearchLab/dfttk/blob/master/docs/Configuration.md. \
            This folder will be ignored.".format(psp_name))
        psp_name_norm = None
    return psp_name_norm

def find_vasp_path(vasp_cmd="vasp_std", template="vaspjob.pbs", queue_type="pbs"):
    """
    Find the location of vasp

    Parameter
        vasp_cmd: str
            The vasp command
        template: str (filename-like)
            The filename of the queue script. Default: vaspjob.pbs
        queue_type: str
            The type of queue system. Default: pbs
    Return
        vasp_path: (filename-like) str
            The dirname of vasp exe file, if not exists, return None
    """

    vasp_path = None

    vasp_path = which(vasp_cmd)

    if not vasp_path:
        warnings.warn("DFTTK can't find vasp(by {}) in the environment, it will try to load it according to queue script. If you have loaded vasp, please specify correct vasp_cmd by -v or --vasp_cmd_flag".format(vasp_cmd))
        if os.path.exists(template):
            param_dict = parse_queue_script(template=template, queue_type=queue_type, vasp_cmd_flag=vasp_cmd)
            if param_dict["pre_rocket"]:
                load_str = ";".join(param_dict["pre_rocket"]) + "; which " + vasp_cmd
                try:
                    vasp_path_popen = subprocess.run(load_str, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                    vasp_path = vasp_path_popen.stdout.decode('utf-8').strip()
                except Exception as e:
                    raise ValueError("The load part in queue script({}) is incorrect.".format(template))
            else:
                raise ValueError("In the queue script ({}), there is not load part. \
                    Please provide correct queue script for vasp or load vasp manual.".format(template))
        else:
            warnings.warn("Queue script doesnot exists, it will try to load vasp automatically.")
            load_modules = ["vasp", "intel impi vasp"]
            for load_module in load_modules:
                load_str = "module load {}; which {}".format(load_module, vasp_cmd)
                try:
                    vasp_path_popen = subprocess.run(load_str, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                    vasp_path = vasp_path_popen.stdout.decode('utf-8').strip()
                    break
                except Exception as e:
                    pass
            if not vasp_path:
                raise EnvironmentError("DFTTK can't not load vasp automatically. Please provide the queue script or load vasp manual.")
    if vasp_path:
        vasp_path = os.path.dirname(vasp_path)
        print("SUCCESSFUL: vasp was found successful, and it is located at {}".format(vasp_path))
    return vasp_path

def find_psppath_in_cluster(vasp_cmd="vasp_std", psp_pathnames=None, template="vaspjob.pbs", queue_type="pbs"):
    """
    Find the location of pseudopotential
    We assumed that the pseudopotential located in the same folder or parent folder of vasp's exe file

    If vasp not loaded, please provide the queue script, and it will parse the script and load vasp

    Parameter
        vasp_cmd: str
            The vasp command, default is 'vasp_std'
        psp_pathnames: str or list(str)
            The possible folder name of the pseudopotential
        template: str (filename-like)
            The filename of the queue script. Default: vaspjob.pbs
        queue_type: str
            The type of queue system. Default: pbs
    Return
        psp_path: list(str)
            The list of folder names of vasp's pseudopotential
    """

    if not psp_pathnames:
        psp_pathnames=["pp", "pps", "psp", "potential", "pseudopotential"]
    if isinstance(psp_pathnames, str):
        psp_pathnames = [psp_pathnames]

    psp_path = []

    #Find vasp's location
    vasp_path = find_vasp_path(vasp_cmd=vasp_cmd, template=template, queue_type=queue_type)

    #Search the vasp_path and its parent path(e.g. the exe file in bin/src folder)
    vasp_path = [vasp_path, os.path.dirname(vasp_path)]
    for vasp_pathi in vasp_path:
        for psp_pathname in psp_pathnames:
            psp_path_tmp = os.path.join(vasp_pathi, psp_pathname)
            if os.path.exists(psp_path_tmp):
                psp_path.append(psp_path_tmp)
                print("SUCCESSFUL: The pseudopotential folder were found, and it is located at {}".format(psp_path_tmp))
    if not psp_path:
        warnings.warn("No folder (named as {}) is found in {}. Please specify correct folder name of pseudopotential by -psp \
            or provide your own pseudopotential and disable -aci parameter.".format(", ".join(psp_pathnames), "\n".join(vasp_path)))
    return psp_path


def handle_potcar_gz(psp_dir=None, path_to_store_psp="psp_pymatgen", aci=True,
    vasp_cmd="vasp_std", template="vaspjob.pbs", queue_type="pbs"):
    """
    Compress and move the pseudopotential to a specified path(path_to_store_psp)
    (The compress is done by running "pmg config -p psp_dir path_to_store_psp" command)

    Parameter
        psp_dir: str (path-like)
            The origial path containing psp. Both original and uncompressed are ok.
            The name of the compressed file or the sub-folder containing psps must be in the following list
            ["potpaw_PBE", "POT_GGA_PAW_PBE","potpaw_PBE_52", "POT_GGA_PAW_PBE_52","potpaw_PBE_54", "POT_GGA_PAW_PBE_54",
             "potpaw_PBE.52", "POT_GGA_PAW_PBE_52","potpaw_PBE.54", "POT_GGA_PAW_PBE_54","potpaw_LDA", "POT_LDA_PAW",
             "potpaw_LDA.52", "POT_LDA_PAW_52","potpaw_LDA.54", "POT_LDA_PAW_54","potpaw_LDA_52", "POT_LDA_PAW_52",
             "potpaw_LDA_54", "POT_LDA_PAW_54","potUSPP_LDA", "POT_LDA_US","potpaw_GGA", "POT_GGA_PAW_PW91",
             "potUSPP_GGA", "POT_GGA_US_PW91"]
            For more details, Ref:https://pymatgen.org/installation.html#potcar-setup
            The example of the structure of the psp_dir:
            e.g. psp_dir
                 ├── potpaw_LDA.54.tar.gz
                 └── potpaw_PBE.54.tar.gz
              or: psp_dir
                  ├── potpaw_LDA_54
                  │   ├── Ac
                  │   ├── Ag
                  │   └── ...
                  ├── potpaw_PBE_54
                  │   ├── Ac
                  │   ├── Ag
                  │   └── ...
                  └── ...
        path_to_store_psp: str (path-like)
            The destination to store the compressed psp. Default: psp_pymatgen
    Return
        None
    """
    def copy_potcar(psp_dir, psp_uncompress, aci_name_map = {"USPP_GAA": "POT_GGA_US_PW91"}):
        flag_copy = False
        for potcar_path in psp_dir:
            if not os.path.exists(potcar_path):
                continue
            file_str = os.listdir(potcar_path)
            for file_i in file_str:
                dst_path_name = parse_psp_name(file_i)
                if not (dst_path_name or file_i in aci_name_map):
                    continue
                if file_i in aci_name_map:
                    dst_path_name = aci_name_map[file_i]
                psp_old = os.path.join(potcar_path, file_i)
                psp_new = os.path.join(psp_uncompress, dst_path_name)
                if os.path.isdir(psp_old):
                    if os.path.exists(psp_new):
                        warnings.warn("Potential({}) exists, and current potential will over write it.".format(psp_new))
                        shutil.rmtree(psp_new)
                    flag_copy = True
                    shutil.copytree(psp_old, psp_new)
                else:
                    creat_folders(psp_new)
                    if file_i.endswith(".tar.gz") or file_i.endswith(".tgz"):
                        os.system("tar -zxvf " + psp_old + " -C " + psp_new)
                        flag_copy = True
                    elif file_i.endswith(".tar"):
                        os.system("tar -xvf " + psp_old + " -C " + psp_new)
                        flag_copy = True
                    else:
                        warnings.warn("Current file ({}) is not supported. The pseudopotential should be uncompressed \
                            or compressed file endi with .tar.gz or .tgz or .tar".format(file_i))
        if not flag_copy:
            warnings.warn("No supported pseudopotential was found in : {}.".format(", ".join(psp_dir)) + \
                "The name rule ref. https://github.com/PhasesResearchLab/dfttk/blob/master/docs/Configuration.md")
        return flag_copy

    if not psp_dir:
        psp_dir=["pp", "pps", "psp", "potential", "pseudopotential"]
    if isinstance(psp_dir, str):
        psp_dir = []

    aci_name_map = {"USPP_GAA": "POT_GGA_US_PW91"}  #A typo in ACI cluster
    psp_uncompress = get_abspath("./psp_uncompress")
    creat_folders(psp_uncompress)

    flag_aci = False
    if aci:
        #For ACI at PSU only
        aci_pp_path = find_psppath_in_cluster(vasp_cmd=vasp_cmd, psp_pathnames=psp_dir, template=template, queue_type=queue_type)
        flag_aci = copy_potcar(aci_pp_path, psp_uncompress, aci_name_map = aci_name_map)


    # file_str is not abspath, is relative path
    flag_user = copy_potcar(psp_dir, psp_uncompress, aci_name_map = aci_name_map)

    if not (flag_aci or flag_user):
        raise FileNotFoundError("No pseudopotential was found, plese provide correct pseudopotential \
            and use -psp parameter to point to correct position")

    # config the POTCAR
    os.system("pmg config -p " + psp_uncompress + " " + path_to_store_psp)
    # Remove the uncompress folder
    try:
        shutil.rmtree(psp_uncompress)
    except:
        os.system("chmod +w " + os.path.join(psp_uncompress, "*/*"))
        shutil.rmtree(psp_uncompress)

def config_pymatgen(psp_dir=None, def_fun="PBE", mapi=None, path_to_store_psp="psp_pymatgen", aci=False,
    vasp_cmd="vasp_std", template="vaspjob.pbs", queue_type="pbs"):
    """
    Config pymatgen.
    If the key is exists in ~/.pmgrc.yaml and not empty, skip

    Parameter
        psp_dir: str (path-like)
            Ref: handle_potcar_gz
        def_fun: str
            The default functional. Default: PBE
        mapi: str
            The API of Materials Project. Default: None. Ref. https://materialsproject.org/open
        path_to_store_psp: str (path-like)
            The destination to store the compressed psp. default: psp_pymatgen
    Return
    """
    keys_required = ["PMG_DEFAULT_FUNCTIONAL", "PMG_MAPI_KEY", "PMG_VASP_PSP_DIR"]
    keys_dict = {"PMG_DEFAULT_FUNCTIONAL": def_fun, "PMG_VASP_PSP_DIR": path_to_store_psp, "PMG_MAPI_KEY": mapi}

    homepath = str(Path.home())

    pmg_config_file = os.path.join(homepath, ".pmgrc.yaml")
    keys_exist = []
    params = {}
    if os.path.exists(pmg_config_file):
        pmg_config = loadfn(pmg_config_file)
        for key in keys_required:
            flag_exist = 0
            key_old = key[4:]   #old style not "PMG_"
            if key_old in pmg_config:
                if pmg_config[key_old]:
                    params[key] = pmg_config[key]
                    flag_exist = 1
            if key in pmg_config:
                if pmg_config[key]:
                    # Not empty or None
                    params[key] = pmg_config[key]
                    flag_exist = 1
            if flag_exist:
                keys_exist.append(key)
        keys_required = list(set(keys_required).difference(set(keys_exist)))
        if len(keys_required) == 0:
            warnings.warn("The pymatgen has been configured before.")
            return
        else:
            #Backup the .pmgrc.yaml file
            shutil.copyfile(pmg_config_file, pmg_config_file + ".dfttk.bak")
    for key in keys_required:
        params[key] = keys_dict[key]
    #dumpfn(params, pmg_config_file, default_flow_style=False)
    dumpfn(params, pmg_config_file)
    if "PMG_MAPI_KEY" in keys_required and (not mapi):
        warnings.warn("'PMG_MAPI_KEY' is empty, some function will not work. " +
            "Please add your own Materials Project's API. " +
            "Ref. https://github.com/PhasesResearchLab/dfttk/tree/master/docs/Configuration.md")
    if "PMG_VASP_PSP_DIR" in keys_required:
        #No configuration for psp path
        handle_potcar_gz(psp_dir=psp_dir, path_to_store_psp=path_to_store_psp, aci=aci,
            vasp_cmd=vasp_cmd, template=template, queue_type=queue_type)

def update_configfile(filename, base_file):
    """
    Update the filename base on base_file.
    Update all except the path/file which exists in filename but not in base_file

    Parameter
        filename: str (filename-like)
            The filename of config file
        base_file: str (filename-like)
            The base file
    Return
        None
    """

    ori_file = loadfn(filename)
    base_file = loadfn(base_file)
    """
    for item in base_file:
        flag_update = True
        if item in ori_file:
            if isinstance(base_file[item], str) and isinstance(ori_file[item], str):
                if os.path.exists(ori_file[item]) and (not os.path.exists(base_file[item])):
                    flag_update = False
        if flag_update:
            ori_file[item] = base_file[item]
    """
    if filename.endswith(".json"):
        dumpfn(ori_file, filename)
    elif filename.endswith(".yaml"):
        #dumpfn(ori_file, filename, default_flow_style=False, indent=4)
        dumpfn(ori_file, filename)

def config_atomate(path_to_store_config=".", config_folder="config", queue_script="vaspjob.pbs",
    queue_type="pbs", vasp_cmd_flag="vasp_std", machine="aci", machines=None,
    nodes=1, ppn=16, pmem="8gb"):
    """
    Configuration for atomate

    Parameter
        path_to_store_config: str (path-like)
            The path to store the configuration files. Default: .
        config_folder: str (path-like)
            The path of config files. Default: config
        queue_script: str (filename-like)
            The submitting script for the queue system. Default: vaspjob.pbs
        queue_type: str
            Th type of queue system. Now, only support pbs. Default: pbs
        vasp_cmd_flag: str
            The flag of vasp_cmd to distinguish the vasp_cmd with other commands in the queue script
    Return
        None
    """
    config_file = get_config_file(config_folder=config_folder, queue_script=queue_script)

    creat_folders(os.path.join(path_to_store_config,"config"))
    creat_folders(os.path.join(path_to_store_config,"logs"))


    if config_file[queue_script]:
        #If the pbs file exists
        param_dict = parse_queue_script(template=config_file[queue_script],
                                        queue_type=queue_type, vasp_cmd_flag=vasp_cmd_flag)
    else:
        param_dict = {}
        param_dict["queue_type"] = queue_type
        param_dict["vasp_cmd_flag"] = vasp_cmd_flag
        param_dict["machine"] = machine
        param_dict["nodes"] = nodes
        param_dict["ppn"] = ppn
        param_dict["machines"] = machines
        param_dict["pmem"] = pmem

    param_dict["path_to_store_config"] = path_to_store_config

    required_file = ["db.json", "my_launchpad.yaml"]
    option_file = ["FW_config.yaml", "my_fworker.yaml", "my_qadapter.yaml"]
    FileModule = {"FW_config.yaml": "ConfigFW", "my_fworker.yaml": "ConfigFworker", "my_qadapter.yaml": "ConfigQadapter",
                  "db.json": "ConfigDb", "my_launchpad.yaml": "ConfigLaunchFile"}
    files = required_file + option_file
    for file in files:
       #print("xxxxxxx", FileModule[file] + "(**param_dict).write_file()", param_dict)
        if file in option_file:
            eval(FileModule[file] + "(**param_dict).write_file()")
        if config_file[file]:
            update_configfile(os.path.join(param_dict["path_to_store_config"], "config", file), config_file[file])
    #Add environment var
    FW_CONFIG_FILE_VAL = os.path.join(path_to_store_config, "config","FW_config.yaml")
    add_path_var(force_override=True, FW_CONFIG_FILE=FW_CONFIG_FILE_VAL)


class ConfigTemplate(object):
    """
    The default parameters is for ACI
    """
    def __init__(self, **kwargs):
        super(ConfigTemplate, self).__init__()
       #The input should be a dict
        PATH_TO_STORE_CONFIG = kwargs.get("path_to_store_config", ".")
        PATH_TO_STORE_CONFIG = get_abspath(PATH_TO_STORE_CONFIG)
        self.PATH_TO_STORE_CONFIG = PATH_TO_STORE_CONFIG
        self.VASP_CMD = kwargs.get("vasp_cmd", "mpirun vasp_std")
        self.NNODES = kwargs.get("nodes", 1)
        self.PPNODE = kwargs.get("ppn", 24)
        self.PMEM = kwargs.get("pmem", "8gb")
        self.C = kwargs.get("constraint", "knl,quad,cache")
        self.WALLTIME = kwargs.get("walltime", "48:00:00")
        self.QUEUE = kwargs.get("queue", "open")
        self.PRE_ROCKET = kwargs.get("pre_rocket", "module load intel impi vasp")
        self.POST_ROCKET = kwargs.get("post_rocket", '')

    def write_file(self):
        filename = os.path.join(self.PATH_TO_STORE_CONFIG, "config", self.FILENAME)
        with open(filename, 'w') as f:
            if filename.endswith(".json"):
                from json import dump
                dump(self.DATA, f)
            elif filename.endswith(".yaml"):
                from yaml import dump
                #dump(self.DATA, f, default_flow_style=False, sort_keys=False, indent=4)
                dump(self.DATA, f, sort_keys=False)

class ConfigDb(ConfigTemplate):
    """docstring for ConfigDb"""
    def __init__(self, **kwargs):
        super(ConfigDb, self).__init__(**kwargs)
        self.FILENAME = "db.json"
        self.DATA = {
            "database": "dfttk_tests",
            "collection": "tasks",
            "host": "localhost",
            "port": 27017,
            "aliases": {}}


class ConfigLaunchFile(ConfigTemplate):
    """docstring for MyLaunchFile"""
    def __init__(self, **kwargs):
        super(ConfigLaunchFile, self).__init__(**kwargs)
        self.FILENAME = "my_launchpad.yaml"
        self.DATA = {"host": "localhost",
            "port": 27017,
            "name": "dfttk-fws",
            "ssl_ca_file": "null",
            "strm_lvl": "INFO",
            "user_indices": "[]",
            "wf_user_indices": "[]"}

class ConfigFW(ConfigTemplate):
    """docstring for ConfigFW"""
    def __init__(self, **kwargs):
        super(ConfigFW, self).__init__(**kwargs)
        self.FILENAME = "FW_config.yaml"
        self.DATA = {"CONFIG_FILE_DIR": os.path.join(self.PATH_TO_STORE_CONFIG, "config"),
            "LAUNCHPAD_LOC": os.path.join(self.PATH_TO_STORE_CONFIG, "config","my_launchpad.yaml"),
            "FWORKER_LOC": os.path.join(self.PATH_TO_STORE_CONFIG, "config","my_fworker.yaml"),
            "QUEUEADAPTER_LOC": os.path.join(self.PATH_TO_STORE_CONFIG, "config","my_qadapter.yaml"),
            "QUEUE_JOBNAME_MAXLEN": 15,
            "ADD_USER_PACKAGES": ["atomate.vasp.firetasks", "atomate.feff.firetasks"]
        }

class ConfigQadapter(ConfigTemplate):
    """docstring for ConfigQadapter"""
    def __init__(self, **kwargs):
        super(ConfigQadapter, self).__init__(**kwargs)
        queue_type = kwargs.get("queue_type", "pbs")
        machine = kwargs.get("machine","aci")
        user_machines = kwargs.get("machines",None)

        self.FILENAME = "my_qadapter.yaml"
        pbs = {"_fw_name": "CommonAdapter",
            "_fw_q_type": "PBS",
            "rocket_launch": "rlaunch -c " + os.path.join(self.PATH_TO_STORE_CONFIG, "config") + " rapidfire",
            "nnodes": self.NNODES,
            "ppnode": self.PPNODE,
            "pmem": self.PMEM,
            "walltime": self.WALLTIME,
            "queue": self.QUEUE,
            "account": "open",
            "job_name": "dfttk",
            "pre_rocket": self.PRE_ROCKET,
            "post_rocket": self.POST_ROCKET,
            "logdir": os.path.join(self.PATH_TO_STORE_CONFIG, "logs")
        }

        slurm = {"_fw_name": "CommonAdapter",
            "_fw_q_type": "SLURM",
            "rocket_launch": "rlaunch -c " + os.path.join(self.PATH_TO_STORE_CONFIG, "config") + " rapidfire",
            "nodes": self.NNODES,
            "ntasks": self.PPNODE,
            "walltime": self.WALLTIME,
            "queue": self.QUEUE,
            "account": "open",
            "job_name": "dfttk",
            "pre_rocket": self.PRE_ROCKET,
            "post_rocket": self.POST_ROCKET,
            "logdir": os.path.join(self.PATH_TO_STORE_CONFIG, "logs")
        }

        machines = get_machines(nodes=self.NNODES, ppn=self.PPNODE, user_machines=user_machines)
        if machine in machines.keys():
            m = machines[machine]
            if "_fw_template_file" in m.keys():
                head, tail = os.path.split(m["_fw_template_file"])
                m["_fw_template_file"] = os.path.join(self.PATH_TO_STORE_CONFIG,"config",tail)
            queue_type = m['_fw_q_type'].lower()
            if queue_type=="slurm": self.DATA = slurm
            else: self.DATA = pbs
            self.DATA.update(m)
        else:
            self.DATA = pbs
            self.DATA.update(machines["aci-roar"])
            print ("machine", machine, "is not in the list",  machines.keys(), "Default to aci-roar")
        #print(self.DATA)


class ConfigFworker(ConfigTemplate):
    """docstring for ConfigFworker"""
    def __init__(self, **kwargs):
        super(ConfigFworker, self).__init__(**kwargs)
        queue_type = kwargs.get("queue_type", "pbs")
        machine = kwargs.get("machine","aci")
        user_machines = kwargs.get("machines",None)

        self.FILENAME = "my_fworker.yaml"
        self.DATA = {"name": "ACI",
            "category": '',
            "query": '{}',
            "env":
                {"db_file": os.path.join(self.PATH_TO_STORE_CONFIG, "config/db.json"),
                #{"db_file": ">>db_file<<",
                 "vasp_cmd": self.VASP_CMD,
                 "scratch_dir": "null",
                 "incar_update": {}}
            }

        machines = get_machines(nodes=self.NNODES, ppn=self.PPNODE, user_machines=user_machines)

        self.DATA["name"] = machine
        if machine in machines.keys():
            self.DATA['env']["vasp_cmd"] = machines[machine]["vasp_cmd"]
        else:
            self.DATA['env']["vasp_cmd"] = machines['aci-roar']["vasp_cmd"]
            print ("machine", machine, "is not in the list",  machines.keys(), "Default to ACI")



def test_config(test_pymagen=True, test_atomate=True):
    if test_pymagen:
        test_config_pymatgen()
    if test_atomate:
        test_config_atomate()

def test_config_pymatgen():
    homepath = str(Path.home())
    path_mp_config = os.path.join(homepath, ".pmgrc.yaml")
    if os.path.exists(path_mp_config):
        mp_config = loadfn(path_mp_config)

        print("##########Start to test the PMG_MAPI_KEY paramter##########")
        help_cmd = "-mapi YOUR_MP_API_KEY"
        param = "PMG_MAPI_KEY"
        if param in mp_config:
            try:
                with MPRester(mp_config[param]) as mpr:
                    mpr.get_structure_by_material_id("mp-66")
                Tips().set_properly(MAPI_KEY=mp_config[param])
            except Exception as e:
                Tips().set_improper(param, help_cmd)
        else:
            Tips().set_not_exist(param, help_cmd)

        print("\n##########Start to test the PMG_DEFAULT_FUNCTIONAL paramter##########")
        help_cmd = "-df DEFAULT_FUNCTIONAL"
        param = "PMG_DEFAULT_FUNCTIONAL"
        flag_functional = False
        FUNCTIONAL_CHOICES = Potcar.FUNCTIONAL_CHOICES
        if param in mp_config:
            DF = mp_config[param]
            if DF in FUNCTIONAL_CHOICES:
                Tips().set_properly(PMG_DEFAULT_FUNCTIONAL=DF)
                flag_functional = True
            else:
                Tips().set_improper(param, help_cmd)
        else:
            Tips().set_not_exist(param, help_cmd)

        print("\n##########Start to test the PMG_VASP_PSP_DIR paramter##########")
        help_cmd = "-psp VASP_PSP_DIR"
        param = "PMG_VASP_PSP_DIR"
        flag_psp = False
        FUNCTIONAL_DIR = list(PotcarSingle.functional_dir.values())
        functional_name = {v: k for k, v in PotcarSingle.functional_dir.items()}
        if param in mp_config:
            psp_dir = mp_config[param]
            if os.path.isdir(psp_dir):
                flag_psp = False
                functional_available = []
                sub_dirs = os.listdir(psp_dir)
                for item in sub_dirs:
                    if item in FUNCTIONAL_DIR:
                        functional = functional_name[item]
                        try:
                            p = PotcarSingle.from_symbol_and_functional("Fe", functional)
                            functional_available.append(functional)
                            flag_psp = True
                        except Exception as e:
                            print("There are some problems of " + functional + " in " + os.path.join(psp_dir, item))
                if flag_psp:
                    Tips().functional_info(param)
                    print("\t The supported functional is/are: " + ", ".join(functional_available))
                    flag_psp = True
                else:
                    print("There is no available functional in " + psp_dir)
                    Tips().set_improper(param, help_cmd)
            else:
                print("The path " + psp_dir + " not exists.")
                Tips().set_improper(param, help_cmd)
        else:
            Tips().set_not_exist(param, help_cmd)
    else:
        Tips().set_not_exist("~/.pmgrc.yaml", "-mp")
    if flag_psp and flag_functional:
        if not (mp_config["PMG_DEFAULT_FUNCTIONAL"] in functional_available):
            warnings.warn("The default functional '{}' is not supported in current available \
                functionals: {}.".format(mp_config["PMG_DEFAULT_FUNCTIONAL"], "\n" + ", ".join(functional_available)))

def test_config_atomate():
    #TODO
    pass

class Tips(Exception):
    """docstring for DfttkConfigError"""
    def __init__(self):
        super(Tips, self).__init__()

    def functional_info(self, param):
        print("SUCCESSFUL: The " + param + " is set properly.")

    def set_properly(self, **kwargs):
        for item in kwargs:
            print("SUCCESSFUL: Your " + item + " is " + kwargs[item])

    def set_improper(self, param, command):
        print("ERROR: The setting of " + param + " is inappropriate. (This is not a valid " + param + ")")
        self.ref(command)

    def set_not_exist(self, param, command):
        print("ERROR: The " + param + " not exists.")
        self.ref(command)

    def ref(self, command):
        print("\t Please config it using 'dfttk config " + command + "'")
        print("\t Ref. https://github.com/hitliaomq/dfttk_tutorial/tree/master/config")
