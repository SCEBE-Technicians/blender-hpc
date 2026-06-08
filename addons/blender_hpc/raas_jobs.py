# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####


import functools
import logging
import tempfile
import os
from pathlib import Path, PurePath
import typing
import json

################################
import time
################################

import bpy
from bpy.types import AddonPreferences, Operator, WindowManager, Scene, PropertyGroup, Panel
from bpy.props import StringProperty, EnumProperty, PointerProperty, BoolProperty, IntProperty

from bpy.types import Header, Menu

import pathlib
import json

import time
import re

################################

from . import async_loop
from . import raas_server
from . import raas_pref
from . import raas_config
from . import raas_connection

################################
log = logging.getLogger(__name__)
################################
class JobTaskInfo:
    def __init__(self, job_cores, ClusterNodeTypeId, CommandTemplateId):
        self.job_cores = job_cores
        self.ClusterNodeTypeId = ClusterNodeTypeId
        self.CommandTemplateId = CommandTemplateId

async def CreateJobTask3Dep(context, 
                            token, 
                            job_task1: JobTaskInfo, 
                            job_task2: JobTaskInfo,
                            job_task3: JobTaskInfo,
                            FileTransferMethodId, 
                            ClusterId):

    blender_job_info_new = context.scene.raas_blender_job_info_new
    job_type = blender_job_info_new.job_type

    preset = raas_pref.get_selected_cluster_preset(context)

    job = None
    username = preset.raas_da_username
    use_xorg = str(job_type == 'ORIGEEVEE' or job_type == 'ORIGWORKBENCH')
    use_mpi1 = context.scene.raas_config_functions.call_get_da_queue_mpi_procs(job_task1.CommandTemplateId)
    use_mpi2 = context.scene.raas_config_functions.call_get_da_queue_mpi_procs(job_task2.CommandTemplateId)
    use_mpi3 = context.scene.raas_config_functions.call_get_da_queue_mpi_procs(job_task3.CommandTemplateId)

    if blender_job_info_new.render_type == 'IMAGE':        
        job_arrays = None
        frame_start = blender_job_info_new.frame_current
        frame_end = blender_job_info_new.frame_current
        max_jobs = 1
        custom_job_arrays = ''
    else:
        frame_start = blender_job_info_new.frame_start
        frame_end = blender_job_info_new.frame_end
        max_jobs = blender_job_info_new.max_jobs
        custom_job_arrays = blender_job_info_new.job_arrays
        #     #                            blender_job_info_new.frame_end, blender_job_info_new.frame_step)
        #     #                            blender_job_info_new.frame_end, blender_job_info_new.frame_step * use_mpi2)

        if len(custom_job_arrays) == 0:
            if max_jobs > (frame_end - frame_start + 1):
                max_jobs = (frame_end - frame_start + 1)        

            if max_jobs < 1:
                job_arrays = None
                max_jobs = 1
            else:
                job_arrays = '%d-%d' % (1, max_jobs)
        else:
            job_arrays = custom_job_arrays

    frame_start = str(frame_start)
    frame_end = str(frame_end)
    max_jobs = str(max_jobs)

    use_mpi1 = str(use_mpi1)
    use_mpi2 = str(use_mpi2)
    use_mpi3 = str(use_mpi3)

    blender_param = raas_connection.convert_path_to_linux(blender_job_info_new.blendfile)
    blender_version = raas_config.GetBlenderClusterVersion()

    job_walltime = blender_job_info_new.job_walltime * 60

    task1 = {
        "Name": blender_job_info_new.job_name,
        "MinCores": job_task1.job_cores,
        "MaxCores": job_task1.job_cores,
        "WalltimeLimit": 1800,
        "StandardOutputFile": 'stdout',
        "StandardErrorFile": 'stderr',
        "ProgressFile": 'stdprog',
        "LogFile": 'stdlog',
        "ClusterNodeTypeId":  job_task1.ClusterNodeTypeId,
        "CommandTemplateId": job_task1.CommandTemplateId,
        "Priority": 4,
        "EnvironmentVariables": [
            {
                "Name": "job_project",
                "Value": blender_job_info_new.job_project
            },
            {
                "Name": "job_email",
                "Value": blender_job_info_new.job_email
            },
            {
                "Name": "frame_start",
                "Value": frame_start
            },
            {
                "Name": "frame_end",
                "Value": frame_end
            },
            {
                "Name": "username",
                "Value": username
            },
            {
                "Name": "blender_version",
                "Value": blender_version
            },
            {
                "Name": "use_xorg",
                "Value": use_xorg
            },
            {
                "Name": "use_mpi",
                "Value": use_mpi1
            },
            {
                "Name": "max_jobs",
                "Value": max_jobs
            },
            {
                "Name": "job_arrays",
                "Value": custom_job_arrays
            }, 
        ],
        "TemplateParameterValues": [
            {
                "CommandParameterIdentifier": "inputParam",
                "ParameterValue": blender_param
            }
        ]
    }

    task2 = {
        "Name": blender_job_info_new.job_name,
        "MinCores": job_task2.job_cores,
        "MaxCores": job_task2.job_cores,
        "WalltimeLimit": job_walltime,
        "StandardOutputFile": 'stdout',
        "StandardErrorFile": 'stderr',
        "ProgressFile": 'stdprog',
        "LogFile": 'stdlog',
        "ClusterNodeTypeId":  job_task2.ClusterNodeTypeId,
        "CommandTemplateId": job_task2.CommandTemplateId,
        "Priority": 4,
        "JobArrays": job_arrays,
        "DependsOn": [
                        task1
        ],
        "EnvironmentVariables": [
            {
                "Name": "job_project",
                "Value": blender_job_info_new.job_project
            },
            {
                "Name": "job_email",
                "Value": blender_job_info_new.job_email
            },
            {
                "Name": "frame_start",
                "Value": frame_start
            },
            {
                "Name": "frame_end",
                "Value": frame_end
            },
            {
                "Name": "blender_version",
                "Value": blender_version
            },
            {
                "Name": "use_xorg",
                "Value": use_xorg
            },
            {
                "Name": "use_mpi",
                "Value": use_mpi2
            },
            {
                "Name": "username",
                "Value": username
            },
            {
                "Name": "max_jobs",
                "Value": max_jobs
            },
            {
                "Name": "job_arrays",
                "Value": custom_job_arrays
            }, 
        ],
        "TemplateParameterValues": [
            {
                "CommandParameterIdentifier": "inputParam",
                "ParameterValue": blender_param
            }
        ]
    }

    task3 = {
        "Name": blender_job_info_new.job_name,
        "MinCores": job_task3.job_cores,
        "MaxCores": job_task3.job_cores,
        "WalltimeLimit": job_walltime,
        "StandardOutputFile": 'stdout',
        "StandardErrorFile": 'stderr',
        "ProgressFile": 'stdprog',
        "LogFile": 'stdlog',
        "ClusterNodeTypeId":  job_task3.ClusterNodeTypeId,
        "CommandTemplateId": job_task3.CommandTemplateId,
        "Priority": 4,
        "DependsOn": [
                        task2
        ],
        "EnvironmentVariables": [
            {
                "Name": "job_project",
                "Value": blender_job_info_new.job_project
            },
            {
                "Name": "job_email",
                "Value": blender_job_info_new.job_email
            },
            {
                "Name": "frame_start",
                "Value": frame_start
            },
            {
                "Name": "frame_end",
                "Value": frame_end
            },
            {
                "Name": "blender_version",
                "Value": blender_version
            },
            {
                "Name": "use_xorg",
                "Value": use_xorg
            },
            {
                "Name": "use_mpi",
                "Value": use_mpi3
            },
            {
                "Name": "max_jobs",
                "Value": max_jobs
            },
            {
                "Name": "job_arrays",
                "Value": custom_job_arrays
            },            
        ],
        "TemplateParameterValues": [
            {
                "CommandParameterIdentifier": "inputParam",
                "ParameterValue": blender_param
            }
        ]
    }

    job = {
        "Name":  blender_job_info_new.job_name,
        "MinCores": job_task1.job_cores,
        "MaxCores": job_task1.job_cores,
        "Priority": 4,
        "Project":  blender_job_info_new.job_project,
        "FileTransferMethodId":  FileTransferMethodId,
        "ClusterId":  ClusterId,
        "EnvironmentVariables":  None,
        "WaitingLimit": 0,
        "WalltimeLimit": job_walltime,
        "Tasks":  [
            task1,
            task2,
            task3
        ]
    }

    data = {
        "JobSpecification": job,
        "SessionCode": token
    }

    item = context.scene.raas_submitted_job_info_ext_new

    # Id : bpy.props.IntProperty(name="Id")
    item.Id = 0
    # Name : bpy.props.StringProperty(name="Name")
    item.Name = blender_job_info_new.job_name
    # State : bpy.props.EnumProperty(items=JobStateExt_items,name="State")
    item.State = "CONFIGURING"
    # Priority : bpy.props.EnumProperty(items=JobPriorityExt_items,name="Priority",default='AVERAGE')
    item.Priority = "AVERAGE"
    # Project : bpy.props.StringProperty(name="Project Name")
    item.Project = blender_job_info_new.job_project
    # CreationTime : bpy.props.StringProperty(name="Creation Time")
    # SubmitTime : bpy.props.StringProperty(name="Submit Time")
    # StartTime : bpy.props.StringProperty(name="Start Time")
    # EndTime : bpy.props.StringProperty(name="End Time")
    # TotalAllocatedTime : bpy.props.FloatProperty(name="totalAllocatedTime")
    # AllParameters : bpy.props.StringProperty(name="allParameters")
    item.AllParameters = raas_server.json_dumps(data)
    # Tasks: bpy.props.StringProperty(name="Tasks")


def CmdCreateSLURMJob(context):
    """Creates a command to submit a Slurm job on cluster.

    Args:
        context (_type_): Blender context.

    Returns:
        str: Slurm command.
    """
    item = context.scene.raas_submitted_job_info_ext_new
    data = json.loads(item.AllParameters)

    job = data['JobSpecification']
    job_name = job['Name']
    job_project = job['Project']
    tasks = job['Tasks']
    cluster_id = job['ClusterId']

    cmd = ''
    task_id = 0
    for task in tasks:
        cluster_node_type_id = task['ClusterNodeTypeId']
        command_template_id = task['CommandTemplateId']
        cores, script = context.scene.raas_config_functions.call_get_da_queue_script(cluster_id, command_template_id)

        pid_name, pid_queue, pid_dir = context.scene.raas_config_functions.call_get_current_pid_info(context, raas_pref.preferences())

        file = task['TemplateParameterValues'][0]['ParameterValue']

        nodes = 1  # int(task['MaxCores'] / cores)

        envs = task['EnvironmentVariables']
        job_env = ''

        if len(envs) > 0:
            for env in envs:
                job_env = job_env + env['Name'] + '=' + env['Value'] + ','

        work_dir = raas_connection.get_direct_access_remote_storage(
            context) + '/' + job_name

        work_dir_stderr = work_dir + '/' + task['StandardErrorFile']
        work_dir_stdout = work_dir + '/' + task['StandardOutputFile']

        mm, ss = divmod(task['WalltimeLimit'], 60)
        hh, mm = divmod(mm, 60)

        walltime = str(hh) + ':' + str(mm) + ':' + str(ss)

        job_array = ''
        if 'JobArrays' in task:
            if not task['JobArrays'] is None:
                job_array = '--array=' + task['JobArrays']

        depends_on = ''
        if 'DependsOn' in task:
            depends_on = ' --dependency=afterok:${_' + str(task_id - 1) + '##* }'
            job_env = job_env + 'depends_on=\"$_' + str(task_id - 1) + '\",'

        job_env = job_env + 'work_dir=' + work_dir

        xorg_true = ''

        custom_flags = context.scene.raas_config_functions.call_get_special_job_flags(context, cluster_id, command_template_id, pid_queue)
        cmd = cmd + '_' + str(task_id) + '=$(echo \' ' + script + ' ' + file + ' \' | sbatch --export=' + job_env + ' --nodes=' + \
            str(nodes) + ' --job-name \"' + job_project + '\" --time=' + walltime + ' --partition=' + pid_queue + \
            custom_flags + ' ' + job_array + ' --error=' + work_dir_stderr + ' --output=' + work_dir_stdout + \
            depends_on + xorg_true + ' ' + script + ' ' + file + '); echo ${_' + str(task_id) + '##* };'

        task_id = task_id + 1

    return cmd

def CmdCreateJob(context):
    return CmdCreateSLURMJob(context)



def CmdCreateStatSLURMJobFile(context, slurm_jobs):
    """Creates a command that requests job's status on cluster and writes it to a particular file.

    Args:
        context (_type_): Blender context.
        slurm_jobs (str): Slurm jobs (their IDs) in a string, divided by '\n'.

    Returns:
        str: Command.
    """
    item = context.scene.raas_submitted_job_info_ext_new
    data = json.loads(item.AllParameters)

    job = data['JobSpecification'] 
    job_name = job['Name']

    cmd = ''

    slurm_jobs = slurm_extract_job_ids(slurm_jobs)
    if not slurm_jobs:
        raise Exception("No Slurm job ids found in sbatch output.")

    # Prefer the render job. A full submit has init, render, finish; partial
    # submits still get a status file for the first submitted job.
    slurm_job = slurm_jobs[1] if len(slurm_jobs) > 1 else slurm_jobs[0]

    if len(slurm_jobs) > 0:
        job_log = raas_connection.get_direct_access_remote_storage(
            context) + '/' + job_name + '.job'
        if context.scene.raas_blender_job_info_new.cluster_type in {'SCEBE', 'ENUCC'}:
            # These direct Slurm targets use squeue-generated job files. The
            # finish script writes the final COMPLETED state when squeue no
            # longer sees the job.
            cmd = cmd + 'squeue -j ' + slurm_job + ' -h -o "%i %j %T %V %S %e" > ' + job_log + ' || true;'
        else:
            # grep -v omits logging of such as slurmID.batch tasks
            cmd = cmd + 'sacct -j ' + slurm_job + ' --format=JobID%20,Jobname%50,state,Submit,start,end | grep -v "\\." > ' \
                + job_log + ';'

    return cmd

def CmdCreateStatJobFile(context, slurm_jobs):
    return CmdCreateStatSLURMJobFile(context, slurm_jobs)


########################################################################################
def slurm_extract_job_ids(output):
    """Extract numeric Slurm job IDs from sbatch output."""
    job_ids = []
    for line in output.splitlines():
        match = re.search(r'\b(\d+)(?:_\d+)?\b', line)
        if match:
            job_ids.append(match.group(1))
    return job_ids


def slurm_map_slurm_status(slurm_status):
    """
    Maps Slurm statuses to the inner ones.
    Args:
        slurm_status (_str_): _Slurm status._

    Returns:
        _int_: _Inner status code._
    """

    # See https://docs.it4i.cz/general/slurm-job-submission-and-execution/#quick-overview-of-common-batch-job-options
    status = 1  #  "CONFIGURING"
    if slurm_status == 'RUNNING' \
        or slurm_status == 'COMPLETING' \
            or slurm_status == 'SUSPENDED' \
                or slurm_status == 'RESIZING' \
                    or slurm_status == 'STAGE_OUT':
        status = 8
    elif slurm_status == 'PENDING' \
        or slurm_status == 'CONFIGURING' \
            or slurm_status == 'REQUEUE_HOLD' \
                or slurm_status == 'REQUEUED' \
                    or slurm_status == 'REQUEUE_FED':
        status = 4
    elif slurm_status == 'CANCELLED' or slurm_status == 'REVOKED':
        status = 64
    elif slurm_status == 'COMPLETED':
        status = 16
    else:
        status = 32  # Failed
    
    return status


def slurm_helper_raas_dict_jobs(id, name, project, cluster_name, job_type, state = None):
    """_Creates a dictionary and fills it with chosen task details_.

    Args:
        id (_int_): _Task inner ID_.
        name (_str_): _Full task name_.
        project (_str_): _Inner task name_.
        cluster_name (_str_): _Cluster name_.
        job_type (_str_): _Job type_.
        state (_str_, optional): _Task status_. Defaults to None.

    Returns:
        _dict_: _Task dictionary._
    """
    item = {}
    item['Id'] = id    
    item['Name'] = name
    item['Project'] = project
    item['ClusterName'] = cluster_name
    if state is not None:
        item['State'] = state
    return item

def slurm_helper_read_slurm_job_array(lines):
    """_Parses lines and calculates the status of the job array_.

    Args:
        lines (_list_): _Lines to read and parse_.

    Returns:
        _tuple_: _Tuple of the calculated status and a number of read lines_.
    """
    if not lines:
        return 1, 1

    index = 0
    line = lines[index]  # Get the first line and parse it
    elements = slurm_split_job_line(line)
    if len(elements) < 4:
        return 1, 1

    slurm_id = elements[1].split('.')  # list
    job_statuses = []
    out_of_range = False

    while(not out_of_range \
            and len(elements) >= 7 \
            and "JobID" not in elements[1] \
                and "----" not in elements[1] \
                    and len(slurm_id[0].split('_')) == 2): 
        if len(slurm_id) != 2:  # For sure, if there is redundant slurm_id.batch or slurm_id.extern
            # Get job status
            job_statuses.append(elements[3])
        # Get a next line and read slurmId
        index += 1
        try:
            line = lines[index]  # may throw index error
            elements = slurm_split_job_line(line)
            if len(elements) < 4:
                out_of_range = True
                continue
            slurm_id = elements[1].split('.') # may throw index error when a blank line is read
        except IndexError:
            out_of_range = True
            

    # Process job_statuses
    final_status = 1
    if not job_statuses:
        return final_status, max(index, 1)
    elif 'FAILED' in job_statuses \
        or 'NODE_FAIL' in job_statuses \
            or 'OUT_OF_MEMORY' in job_statuses \
                or 'PREEMPTED' in job_statuses \
                    or 'TIMEOUT' in job_statuses \
                    or 'SIGNALING' in job_statuses:
        final_status = 32  # Failed
    elif 'CANCELLED' in job_statuses or 'REVOKED' in job_statuses:
        final_status = 64
    elif 'RUNNING' in job_statuses:
        final_status = 8
    elif 'PENDING' in job_statuses or 'REQUEUED' in job_statuses or 'CONFIGURING' in job_statuses:
        final_status = 4
    # converting a list to a set removes all duplicate values - anything greater than 1 is wrong    
    elif 'COMPLETED' == job_statuses[0] and len(set(job_statuses)) == 1:
        final_status = 16
        
    return final_status, index

def slurm_parse_slurm_job_lines(output, cluster_type, job_type):
    """Parse Slurm job output lines into job data structures.
    
    Args:
        output: Raw command output
        cluster_type: Type of cluster
        
    Returns:
        List of job dictionaries
    """
    lines = [line for line in output.split('\n') if line.strip()]
    if not lines:
        return []
    
    jobs_data = []
    jobs_dict = {}
    job_index = 0
    line_idx = 0
    
    while line_idx < len(lines):
        line = lines[line_idx]
        elements = slurm_split_job_line(line)
        
        if len(elements) < 2:
            line_idx += 1
            continue
            
        try:
            job_name = slurm_get_job_name(elements)
            slurm_id_parts = elements[1].split('.')
        except IndexError:
            line_idx += 1
            continue
        
        # Skip header and separator lines
        if slurm_is_header_or_separator_line(elements):
            line_idx += 1
            continue
            
        # Process different types of job entries
        job_data, lines_consumed = slurm_process_job_entry(
            lines[line_idx:], job_name, elements, slurm_id_parts, 
            cluster_type, job_type, jobs_dict, job_index
        )
        
        if job_data:
            if job_name not in jobs_dict:
                jobs_dict[job_name] = job_data
                jobs_data.append(job_data)
                job_index += 1
            else:
                # Update existing job data
                jobs_dict[job_name].update(job_data)
        
        line_idx += lines_consumed

    return jobs_data


def slurm_split_job_line(line):
    """Split grep-prefixed .job lines while preserving the job file name."""
    elements = line.split()
    if not elements:
        return elements

    if ':' in elements[0]:
        job_file, first_value = elements[0].split(':', 1)
        elements[0] = job_file
        if first_value:
            elements.insert(1, first_value)

    return elements


def slurm_get_job_name(elements):
    """Get the blender-hpc job directory name from a parsed .job line."""
    if elements[0].endswith('.job'):
        return elements[0][:-4]
    return elements[0].split(".")[0]


def slurm_is_header_or_separator_line(elements):
    """Check if line is a header or separator line."""
    return (len(elements) > 1 and 
            ("JobID" in elements[1] or "----" in elements[1]))


def slurm_process_job_entry(lines, job_name, elements, slurm_id_parts, cluster_type, job_type, jobs_dict, job_index):
    """Process a single job entry and return job data and lines consumed.
    
    Returns:
        Tuple of (job_data_dict, lines_consumed)
    """
    if len(elements) < 7:
        if cluster_type == 'SCEBE' and len(elements) >= 6:
            return slurm_process_scebe_job(job_name, elements, cluster_type, job_type, job_index), 1
        return None, 1
    
    # Check for job arrays
    if len(slurm_id_parts[0].split('_')) > 1:
        return slurm_process_job_array(lines, job_name, elements, cluster_type, job_type, job_index)
    
    # Check for regular job entries
    if (len(slurm_id_parts) == 1 and len(elements) == 7 and
        "JobID" not in elements[1] and "----" not in elements[1]):
        return slurm_process_regular_job(job_name, elements, cluster_type, job_type, job_index), 1
    
    # Check for submitted jobs (lines with only separators)
    if slurm_is_separator_only_line(elements, lines):
        return slurm_process_submitted_job(job_name, elements, cluster_type, job_type, job_index), 1
    
    return None, 1


def slurm_process_scebe_job(job_name, elements, cluster_type, job_type, job_index):
    """Process SCEBE squeue/fallback job entries."""
    status = slurm_map_slurm_status(elements[3])
    project_name = elements[2]

    job_data = slurm_helper_raas_dict_jobs(job_index, job_name, project_name, cluster_type, job_type, status)
    job_data.update({
        'CreationTime': elements[4],
        'SubmitTime': elements[4],
        'StartTime': elements[5],
        'EndTime': elements[6] if len(elements) > 6 else 'unknown'
    })

    return job_data


def slurm_process_job_array(lines, job_name, elements, cluster_type, job_type, job_index):
    """Process job array entries."""
    final_status, lines_consumed = slurm_helper_read_slurm_job_array(lines)
    
    project_name = elements[2] if len(elements) > 2 else job_name.split('-')[-1]
    job_data = slurm_helper_raas_dict_jobs(job_index, job_name, project_name, cluster_type, job_type, final_status)
    
    # Add timing information if available
    if len(elements) >= 7:
        job_data.update({
            'CreationTime': elements[4],
            'SubmitTime': elements[4],
            'StartTime': elements[5],
            'EndTime': elements[6]
        })
    
    return job_data, lines_consumed


def slurm_process_regular_job(job_name, elements, cluster_type, job_type, job_index):
    """Process regular job entries."""
    status = slurm_map_slurm_status(elements[3])
    project_name = elements[2]
    
    job_data = slurm_helper_raas_dict_jobs(job_index, job_name, project_name, cluster_type, job_type, status)
    job_data.update({
        'CreationTime': elements[4],
        'SubmitTime': elements[4],
        'StartTime': elements[5],
        'EndTime': elements[6]
    })
    
    return job_data


def slurm_process_submitted_job(job_name, elements, cluster_type, job_type, job_index):
    """Process submitted job entries (jobs that haven't started yet)."""
    # Extract project name from job name
    name_parts = job_name.split('-')
    if len(name_parts) >= 4:
        project_name = '-'.join(name_parts[4:])  # Everything after the timestamp and ID
    else:
        project_name = job_name
    
    return slurm_helper_raas_dict_jobs(job_index, job_name, project_name, cluster_type, job_type, 2)  # SUBMITTED


def slurm_is_separator_only_line(elements, lines):
    """Check if current line contains only separators and next line is different job."""
    if len(elements) < 2:
        return False
        
    # Check if most elements contain separators
    separator_count = sum(1 for e in elements[1:] if "----" in e)
    has_separators = separator_count > len(elements[1:]) // 2
    
    if not has_separators or len(lines) < 2:
        return False
    
    # Check if next line is a different job
    next_elements = lines[1].split()
    if len(next_elements) < 1:
        return False
        
    current_job = elements[0].split('.')[0]
    next_job = next_elements[0].split('.')[0]
    
    return current_job != next_job

#########################################################################################

def update_job_list(context, jobs_data):
    """Update the UI job list with parsed job data."""
    context.scene.raas_list_jobs.clear()
    
    # Add jobs in reverse order (newest first)
    for job_data in reversed(jobs_data):
        item = context.scene.raas_list_jobs.add()
        raas_server.fill_items(item, job_data)
        
        # Load blender_job_info from job.info file
        job_name = job_data.get('Name')
        if job_name:
            job_info_path = raas_connection.get_job_local_storage(job_name) / 'job' / 'job.info'
            if job_info_path.exists():
                try:
                    with open(job_info_path, 'r') as f:
                        job_info_dict = json.load(f)

                    item.blender_job_info_json = json.dumps(job_info_dict)

                except Exception as e:
                    print(f"Failed to load job.info for {job_name}: {e}")
    
    # Ensure index is valid
    max_index = len(context.scene.raas_list_jobs) - 1
    if context.scene.raas_list_jobs_index > max_index:
        context.scene.raas_list_jobs_index = max_index


#########################################################################################
