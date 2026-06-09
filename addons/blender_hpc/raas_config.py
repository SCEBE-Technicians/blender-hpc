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

# (c) IT4Innovations, VSB-TUO

"""ENUCC/SCEBE RaaS config."""

import bpy

REMOTE_ADDON_DIR = 'blender-hpc'

Cluster_items_dict = {
    "SCEBE": "SCEBE GPU Server",
    "ENUCC": "ENUCC",
}

Cluster_items = [
    ("SCEBE", "SCEBE GPU Server", ""),
    ("ENUCC", "ENUCC", ""),
]

Scebe_partitions = [
    ("LocalQ", "LocalQ", ""),
]

Enucc_partitions = [
    ("short", "short", "1 day walltime limit"),
    ("long", "long", "7 day walltime limit"),
    ("himem", "himem", "High-memory nodes"),
    ("gpu", "gpu", "GPU nodes"),
]

JobQueue_items = [
    ("JOB_CPU", "CPU", ""),
    ("JOB_GPU", "GPU", ""),
]

JobQueue_items_dict = {
    "JOB_CPU": "CPU",
    "JOB_GPU": "GPU",
}

from . import raas_jobs
from . import raas_connection

ssh_library_items = [
    ("PARAMIKO", "Paramiko", ""),
    ("SYSTEM", "System", ""),
    ("ASYNCSSH", "AsyncSSH", ""),
]


def GetBlenderClusterVersion():
    return (str(bpy.app.version_string)).replace(' ', '_')


async def CreateJob(context, token):
    blender_job_info_new = context.scene.raas_blender_job_info_new
    job_type = blender_job_info_new.job_type

    if blender_job_info_new.cluster_type not in {'SCEBE', 'ENUCC'}:
        raise ValueError("Unsupported cluster type: %s" % blender_job_info_new.cluster_type)

    if blender_job_info_new.cluster_type == 'ENUCC':
        cluster_id = 13
        cpu_init = 130
        cpu_render = 131
        cpu_finish = 132
        gpu_init = 133
        gpu_render = 134
        gpu_finish = 135
    else:
        cluster_id = 12
        cpu_init = 120
        cpu_render = 121
        cpu_finish = 122
        gpu_init = 123
        gpu_render = 124
        gpu_finish = 125

    if 'JOB_CPU' in job_type:
        await raas_jobs.CreateJobTask3Dep(
            context,
            token,
            raas_jobs.JobTaskInfo(1, cpu_render, cpu_init),
            raas_jobs.JobTaskInfo(1, cpu_render, cpu_render),
            raas_jobs.JobTaskInfo(1, cpu_render, cpu_finish),
            2,
            cluster_id,
        )
    elif 'JOB_GPU' in job_type:
        await raas_jobs.CreateJobTask3Dep(
            context,
            token,
            raas_jobs.JobTaskInfo(1, gpu_render, gpu_init),
            raas_jobs.JobTaskInfo(1, gpu_render, gpu_render),
            raas_jobs.JobTaskInfo(1, gpu_render, gpu_finish),
            2,
            cluster_id,
        )


def GetServer(pid):
    return ""  # TODO


def GetServerFromType(cluster_type):
    if cluster_type == 'SCEBE':
        return '146.176.131.129'
    if cluster_type == 'ENUCC':
        return 'login.enucc.napier.ac.uk'
    raise ValueError("Unsupported cluster type: %s" % cluster_type)


def GetSchedulerFromContext(context):
    blender_job_info_new = context.scene.raas_blender_job_info_new
    if blender_job_info_new.cluster_type in {'SCEBE', 'ENUCC'}:
        return 'SLURM'
    raise ValueError("Unsupported cluster type: %s" % blender_job_info_new.cluster_type)


def GetDAServer(context):
    blender_job_info_new = context.scene.raas_blender_job_info_new
    return GetServerFromType(blender_job_info_new.cluster_type)


def GetDAClusterPath(context, project_dir, pid):
    return project_dir + '/' + REMOTE_ADDON_DIR + '/direct'


def GetDAOpenCallProject(pid):
    return pid


def GetDAQueueMPIProcs(CommandTemplateId):
    if CommandTemplateId in {124, 134}:
        return 1  # GPUs
    return 0


# return cores,queue,script
def GetDAQueueScript(ClusterId, CommandTemplateId):
    if ClusterId == 12 and CommandTemplateId == 120:
        return 1, '~/' + REMOTE_ADDON_DIR + '/scripts/scebe-gpu-server-slurm/job_init.sh'
    elif ClusterId == 12 and CommandTemplateId == 121:
        return 1, '~/' + REMOTE_ADDON_DIR + '/scripts/scebe-gpu-server-slurm/run_blender_cpu.sh'
    elif ClusterId == 12 and CommandTemplateId == 122:
        return 1, '~/' + REMOTE_ADDON_DIR + '/scripts/scebe-gpu-server-slurm/job_finish.sh'
    elif ClusterId == 12 and CommandTemplateId == 123:
        return 1, '~/' + REMOTE_ADDON_DIR + '/scripts/scebe-gpu-server-slurm/job_init.sh'
    elif ClusterId == 12 and CommandTemplateId == 124:
        return 1, '~/' + REMOTE_ADDON_DIR + '/scripts/scebe-gpu-server-slurm/run_blender_gpu.sh'
    elif ClusterId == 12 and CommandTemplateId == 125:
        return 1, '~/' + REMOTE_ADDON_DIR + '/scripts/scebe-gpu-server-slurm/job_finish.sh'
    elif ClusterId == 13 and CommandTemplateId == 130:
        return 1, '~/' + REMOTE_ADDON_DIR + '/scripts/enucc-slurm/job_init.sh'
    elif ClusterId == 13 and CommandTemplateId == 131:
        return 1, '~/' + REMOTE_ADDON_DIR + '/scripts/enucc-slurm/run_blender_cpu.sh'
    elif ClusterId == 13 and CommandTemplateId == 132:
        return 1, '~/' + REMOTE_ADDON_DIR + '/scripts/enucc-slurm/job_finish.sh'
    elif ClusterId == 13 and CommandTemplateId == 133:
        return 1, '~/' + REMOTE_ADDON_DIR + '/scripts/enucc-slurm/job_init.sh'
    elif ClusterId == 13 and CommandTemplateId == 134:
        return 1, '~/' + REMOTE_ADDON_DIR + '/scripts/enucc-slurm/run_blender_gpu.sh'
    elif ClusterId == 13 and CommandTemplateId == 135:
        return 1, '~/' + REMOTE_ADDON_DIR + '/scripts/enucc-slurm/job_finish.sh'

    return None, None


def GetDAJobSpecialFlags(context, ClusterId, CommandTemplateId, pid_queue):
    custom_flags = ''
    if ClusterId in {12, 13} and 'JOB_GPU' in context.scene.raas_blender_job_info_new.job_type:
        custom_flags += ' --gres=gpu:1'
    return custom_flags


def GetGitAddonCommand(repository, branch):
    return 'if [ -d ~/' + REMOTE_ADDON_DIR + ' ] ; then rm -rf ~/' + REMOTE_ADDON_DIR + ' ; fi ; git clone -q -b ' + branch + ' ' + repository + ' ~/' + REMOTE_ADDON_DIR


def GetBlenderInstallCommand(preset, url_link):
    filename = url_link.split('/')[-1]
    extracted_string = filename.replace('.tar.xz', '')

    return 'if [ -d ~/blender ] ; then rm -rf ~/blender ; fi ; \
        cd ~/ ; wget -O blender.tar.xz -q %s ; \
        tar -xf blender.tar.xz ; mv %s ~/blender ; rm blender.tar.xz ; \
            ' % (url_link, extracted_string)


def GetBlenderPatchCommand(preset, url_link):
    return ''


def GetCurrentPidInfo(context, preferences):
    blender_job_info_new = context.scene.raas_blender_job_info_new
    name = blender_job_info_new.cluster_type
    queue = blender_job_info_new.job_partition
    dir = blender_job_info_new.job_remote_dir

    return name, queue, dir


def SetPidDir(preset):
    if preset.cluster_name not in {"SCEBE", "ENUCC"}:
        raise Exception("Unknown cluster name")

    cmd = 'echo $HOME'
    server = GetServerFromType(preset.cluster_name.upper())
    res = raas_connection.ssh_command_sync(server, cmd, preset)
    preset.working_dir = res.strip()


class RaasConfigFunctions:
    """Class that holds pointers to all functions."""

    def __init__(self):
        self.create_job = CreateJob
        self.get_server_from_type = GetServerFromType
        self.get_scheduler_from_context = GetSchedulerFromContext
        self.get_da_server = GetDAServer
        self.get_da_cluster_path = GetDAClusterPath
        self.get_da_open_call_project = GetDAOpenCallProject
        self.get_da_queue_mpi_procs = GetDAQueueMPIProcs
        self.get_da_queue_script = GetDAQueueScript
        self.get_special_job_flags = GetDAJobSpecialFlags
        self.get_git_addon_command = GetGitAddonCommand
        self.get_blender_install_command = GetBlenderInstallCommand
        self.get_blender_patch_command = GetBlenderPatchCommand
        self.get_current_pid_info = GetCurrentPidInfo
        self.set_pid_dir = SetPidDir

    async def call_create_job(self, context, token):
        return await self.create_job(context, token)

    def call_get_server_from_type(self, cluster_type):
        return self.get_server_from_type(cluster_type)

    def call_get_scheduler_from_context(self, context):
        return self.get_scheduler_from_context(context)

    def call_get_da_server(self, context):
        return self.get_da_server(context)

    def call_get_da_cluster_path(self, context, project_dir, pid):
        return self.get_da_cluster_path(context, project_dir, pid)

    def call_get_da_open_call_project(self, pid):
        return self.get_da_open_call_project(pid)

    def call_get_da_queue_mpi_procs(self, command_template_id):
        return self.get_da_queue_mpi_procs(command_template_id)

    def call_get_da_queue_script(self, cluster_id, command_template_id):
        return self.get_da_queue_script(cluster_id, command_template_id)

    def call_get_special_job_flags(self, context, cluster_id, command_template_id, pid_queue):
        return self.get_special_job_flags(context, cluster_id, command_template_id, pid_queue)

    def call_get_git_addon_command(self, repository, branch):
        return self.get_git_addon_command(repository, branch)

    def call_get_blender_install_command(self, preset, url_link):
        return self.get_blender_install_command(preset, url_link)

    def call_get_blender_patch_command(self, preset, url_link):
        return self.get_blender_patch_command(preset, url_link)

    def call_get_current_pid_info(self, context, preferences):
        return self.get_current_pid_info(context, preferences)

    def call_set_pid_dir(self, preset):
        return self.set_pid_dir(preset)
