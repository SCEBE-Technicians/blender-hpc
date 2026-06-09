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


import importlib
import sys
import subprocess
from collections import namedtuple
import functools
import logging
import os.path
import tempfile

import datetime
import typing

import bpy
from bpy.types import AddonPreferences, Operator, WindowManager, Scene, PropertyGroup
from bpy.props import StringProperty, EnumProperty, PointerProperty, BoolProperty, IntProperty
import rna_prop_ui

from . import async_loop
from . import raas_server
from . import raas_config
from . import raas_connection

ADDON_NAME = 'blender_hpc'
DEPENDENCIES_PATH = bpy.utils.user_resource(
    'SCRIPTS', path=os.path.join(ADDON_NAME, "dependencies"), create=True)

log = logging.getLogger(__name__)


@functools.lru_cache()
def factor(factor: float) -> dict:
    """Construct keyword argument for UILayout.split().

    On Blender 2.8 this returns {'factor': factor}, and on earlier Blenders it returns
    {'percentage': factor}.
    """
    if bpy.app.version < (2, 80, 0):
        return {'percentage': factor}
    return {'factor': factor}


##################################################


def show_message_box(message="", title="blender-hpc", icon='INFO'):
    def draw(self, context):
        self.layout.label(text=message)

    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)


##################################################

Dependency = namedtuple("Dependency", ["module", "package", "name"])
python_dependencies = (Dependency(module="paramiko", package="paramiko", name=None),
                       Dependency(module="scp", package="scp", name=None),
                       Dependency(module="asyncssh", package="asyncssh", name=None),
                       )


internal_dependencies = []


def ensure_dependencies_path():
    if DEPENDENCIES_PATH not in sys.path:
        sys.path.insert(0, DEPENDENCIES_PATH)


def import_module(module_name, global_name=None, reload=True):
    ensure_dependencies_path()

    if global_name is None:
        global_name = module_name

    if global_name in globals():
        importlib.reload(globals()[global_name])
    else:
        # Attempt to import the module and assign it to globals dictionary. This allow to access the module under
        # the given name, just like the regular import would.
        globals()[global_name] = importlib.import_module(module_name)


def install_pip():
    try:
        if bpy.app.version < (2, 90, 0):
            python_exe = bpy.app.binary_path_python
        else:
            python_exe = sys.executable

        # Check if pip is already installed
        subprocess.run([python_exe, "-m", "pip", "--version"],
                       check=True, capture_output=True, text=True)

    except subprocess.CalledProcessError:
        import ensurepip

        ensurepip.bootstrap(user=True)
        os.environ.pop("PIP_REQ_TRACKER", None)


def install_and_import_module(module_name, package_name=None, global_name=None):
    if package_name is None:
        package_name = module_name

    if global_name is None:
        global_name = module_name

    # Create a copy of the environment variables and modify them for the subprocess call
    environ_copy = dict(os.environ)
    environ_copy["PYTHONNOUSERSITE"] = "1"

    if bpy.app.version < (2, 90, 0):
        python_exe = bpy.app.binary_path_python
    else:
        python_exe = sys.executable

    os.makedirs(DEPENDENCIES_PATH, exist_ok=True)
    log.info("Installing %s into %s", package_name, DEPENDENCIES_PATH)
    try:
        subprocess.run([python_exe, "-m", "pip", "install",
                        "--target", DEPENDENCIES_PATH, package_name],
                       check=True, env=environ_copy, capture_output=True, text=True)
    except subprocess.CalledProcessError as err:
        log.error("Dependency install failed for %s\nstdout:\n%s\nstderr:\n%s",
                  package_name, err.stdout, err.stderr)
        raise

    # The installation succeeded, attempt to import the module again
    import_module(module_name, global_name)


################################################################


class RAAS_OT_install_scripts(Operator):
    bl_idname = 'raas.install_scripts'
    bl_label = 'Install scripts on the cluster'
    bl_description = ("Install scripts")

    def execute(self, context):
        scripts_installed = False
        for cl in raas_config.Cluster_items:
            try:

                for p in preferences().cluster_presets:
                    if p.cluster_name == cl[0] and p.is_enabled:
                        # TODO: MJ
                        if not preferences().check_valid_settings(p, type='INSTALL_SCRIPTS'):
                            return {"CANCELLED"}

                        # Install scripts
                        self.report({'INFO'}, "Install scripts on '%s'" % (cl[0]))
                        cmd = context.scene.raas_config_functions.call_get_git_addon_command(
                            preferences().raas_scripts_repository, preferences().raas_scripts_repository_branch)
                        if len(cmd) > 0:
                            server = context.scene.raas_config_functions.call_get_server_from_type(cl[0])
                            log.info("Install scripts on %s with command: %s", cl[0], cmd)
                            res = raas_connection.ssh_command_sync(server, cmd, p)
                            log.info("Install scripts on %s result: %s", cl[0], res.strip())

                            script_dir = 'scebe-gpu-server-slurm' if cl[0] == 'SCEBE' else 'enucc-slurm'
                            check_cmd = 'test -d ~/blender-hpc/scripts/%s && echo OK' % script_dir
                            res = raas_connection.ssh_command_sync(server, check_cmd, p)
                            if res.strip() != 'OK':
                                raise Exception("Scripts were not found after install: ~/blender-hpc/scripts/%s" % script_dir)

                        # Install Blender
                        self.report({'INFO'}, "Install Blender on '%s'" % (cl[0]))
                        cmd = context.scene.raas_config_functions.call_get_blender_install_command(p,
                                                                                                   preferences().raas_blender_link)
                        if len(cmd) > 0:
                            server = context.scene.raas_config_functions.call_get_server_from_type(cl[0])
                            log.info("Install Blender on %s with command: %s", cl[0], cmd)
                            res = raas_connection.ssh_command_sync(server, cmd, p)
                            log.info("Install Blender on %s result: %s", cl[0], res.strip())

                        # Apply patches
                        self.report({'INFO'}, "Apply patches on '%s'" % (cl[0]))
                        cmd = context.scene.raas_config_functions.call_get_blender_patch_command(p,
                                                                                                 preferences().raas_blender_link)
                        if len(cmd) > 0:
                            server = context.scene.raas_config_functions.call_get_server_from_type(cl[0])
                            raas_connection.ssh_command_sync(server, cmd, p)

                        preferences().raas_scripts_installed = True
                        scripts_installed = True

                        break

            except Exception as e:
                import traceback
                traceback.print_exc()
                log.exception("Problem with %s on %s", self.bl_label, cl[0])

                self.report({'ERROR'}, "Problem with %s: %s: %s" %
                            (self.bl_label, e.__class__, e))
                self.report({'ERROR'}, "Scripts could not be installed.")
                return {"CANCELLED"}

        if not scripts_installed:
            message = "No enabled cluster preset was found for script installation."
            log.error(message)
            self.report({'ERROR'}, message)
            return {"CANCELLED"}

        log.info("'%s' finished", self.bl_label)
        self.report({'INFO'}, "'%s' finished" % (self.bl_label))
        return {"FINISHED"}


#                 #     return {"CANCELLED"}

#                     #if (cl[0], True) in presets_tuples:
#                         # TODO: MJ


#                 traceback.print_exc()


##################################################################


class RAAS_OT_install_dependencies(Operator):
    bl_idname = 'raas.install_dependencies'
    bl_label = 'Install dependencies'
    bl_description = ("Downloads and installs the required python packages for this add-on. "
                      "Internet connection is required. Blender may have to be started with "
                      "elevated permissions in order to install the package")

    def execute(self, context):
        try:
            install_pip()
            for dependency in python_dependencies:
                install_and_import_module(module_name=dependency.module,
                                          package_name=dependency.package,
                                          global_name=dependency.name)

            # enable_internal_addons()
            # install_external_addons()

        except (subprocess.CalledProcessError, ImportError) as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}

        preferences().dependencies_installed = True

        # Register the panels, operators, etc. since dependencies are installed
        # sim_scene.register()

        self.report({'INFO'}, "'%s' finished" % (self.bl_label))
        return {"FINISHED"}


class RAAS_OT_update_dependencies(Operator):
    bl_idname = 'raas.update_dependencies'
    bl_label = 'Update dependencies'
    bl_description = ("Downloads and installs the required python packages for this add-on. "
                      "Internet connection is required. Blender may have to be started with "
                      "elevated permissions in order to install the package")

    def execute(self, context):
        try:
            install_pip()
            for dependency in python_dependencies:
                install_and_import_module(module_name=dependency.module,
                                          package_name=dependency.package,
                                          global_name=dependency.name)

            # enable_internal_addons()
            # install_external_addons()

        except (subprocess.CalledProcessError, ImportError) as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}

        preferences().dependencies_installed = True

        # Register the panels, operators, etc. since dependencies are installed
        # sim_scene.register()

        self.report({'INFO'}, "'%s' finished" % (self.bl_label))
        return {"FINISHED"}


##################################################

class RAAS_OT_NewClusterPreset(bpy.types.Operator):
    """Create a new cluster preset"""
    bl_idname = "pref.newcluster"
    bl_label = "Add a new cluster"

    def draw(self, context):
        layout = self.layout

    def execute(self, context):
        addonprefs = preferences()
        preset = addonprefs.cluster_presets.add()  # New preset
        if not preset.raas_da_use_password:
            raas_connection.get_preset_private_key_file(preset)

        return {'FINISHED'}


class RAAS_OT_RemoveClusterPreset(bpy.types.Operator):
    """Removes a cluster preset"""
    bl_idname = "pref.removecluster"
    bl_label = ""

    index: bpy.props.IntProperty()

    def draw(self, context):
        layout = self.layout

    def execute(self, context):
        addonprefs = preferences()
        addonprefs.cluster_presets.remove(self.index)  # Remove this preset

        return {'FINISHED'}


def cluster_partition_settings_callback(self, context):
    """Returns a list partitions dynamically based on the cluster selected.

    Returns:
        _list_: _A list of cluster partitions._
    """
    tmp = [cl[0] for cl in raas_config.Cluster_items]
    if self.cluster_name not in tmp:
        return []
    else:
        return getattr(raas_config, "%s_partitions" % self.cluster_name.capitalize())


def enforce_enucc_job_type(self, context):
    if self.cluster_name != 'ENUCC':
        return

    job_type = 'JOB_GPU' if self.partition_name == 'gpu' else 'JOB_CPU'
    if self.job_type != job_type:
        self.job_type = job_type


class ClusterPresets(bpy.types.PropertyGroup):
    """
        A property group of cluster presets. Each presets has the following properties:
        cluster_name, partition_name (queue), is_enabled, working_dir.
    """

    cluster_name: bpy.props.EnumProperty(
        name="Cluster",
        description="Select a cluster",
        items=raas_config.Cluster_items,
        update=enforce_enucc_job_type
    )  # type: ignore

    partition_name: bpy.props.EnumProperty(
        name="Partition/Queue",
        description="Select a partition/queue",
        items=cluster_partition_settings_callback,
        update=enforce_enucc_job_type
    )  # type: ignore

    job_type: bpy.props.EnumProperty(
        items=raas_config.JobQueue_items,
        name="Type of Job (resources)",
        update=enforce_enucc_job_type
    )  # type: ignore

    is_enabled: bpy.props.BoolProperty(
        name="Enabled",
        description="This settings is active",
        default=True
    )  # type: ignore

    working_dir: StringProperty(
        name='Project Dir',
        description='The PROJECT data storage is a central storage for projects/users data',
        default=''
    )  # type: ignore

    raas_da_username: StringProperty(
        name='Username',
        default=''
    )  # type: ignore

    raas_da_password: StringProperty(
        name='Password',
        default='',
        subtype='PASSWORD'
    )  # type: ignore

    raas_da_use_password: bpy.props.BoolProperty(
        name="Use Password",
        default=False
    )  # type: ignore

    raas_private_key_path: StringProperty(
        name='Private Key Path',
        description='Private Key Path',
        subtype='FILE_PATH',
        default=''
    )  # type: ignore

    raas_private_key_password: StringProperty(
        name='Key Passphrase',
        default='',
        subtype='PASSWORD'
    )  # type: ignore

    raas_ssh_library: EnumProperty(
        name='SSH Library',
        items=raas_config.ssh_library_items
    )  # type: ignore


class RAAS_OT_find_working_dir(Operator):
    """
        Goes through all cluster presets and for each finds the remote working directory.
    """
    bl_idname = 'raas.find_working_dir'
    bl_label = 'Find Working Dirs'
    bl_description = ("Find")

    def execute(self, context):
        try:
            # Get the cluster presets
            addonprefs = preferences()
            for preset in addonprefs.cluster_presets:
                if not preferences().check_valid_settings(preset, type='PROJECT_DIR'):
                    message = "Find working dir for %s cancelled: invalid settings" % preset.cluster_name
                    log.error(message)
                    self.report({'ERROR'}, message)
                    return {"CANCELLED"}

                if len(preset.working_dir) == 0:
                    context.scene.raas_config_functions.call_set_pid_dir(preset)  # sets the working_dir in the preset
                    message = "Find working dir for %s: %s" % (preset.cluster_name, preset.working_dir)
                    log.info(message)
                    self.report({'INFO'}, message)
                elif preset.working_dir:
                    message = "Find working dir for %s skipped: already set to %s" % (preset.cluster_name,
                                                                                      preset.working_dir)
                    log.info(message)
                    self.report({'INFO'}, message)
                # # Test connection

        except Exception as e:
            import traceback
            traceback.print_exc()
            log.exception("Problem with %s", self.bl_label)

            self.report({'ERROR'}, "Problem with %s: %s: %s" %
                        (self.bl_label, e.__class__, e))

        log.info("'%s' finished", self.bl_label)
        self.report({'INFO'}, "'%s' finished" % (self.bl_label))
        return {"FINISHED"}


class RAAS_OT_test_connection(Operator):
    """
        Goes through all cluster presets and for each tests the connection.
    """
    bl_idname = 'raas.test_connection'
    bl_label = 'Test Connections'
    bl_description = ("Test")

    def execute(self, context):
        try:
            # Get the cluster presets
            addonprefs = preferences()
            for preset in addonprefs.cluster_presets:

                # Test connection
                if preset.is_enabled:
                    server = context.scene.raas_config_functions.call_get_server_from_type(preset.cluster_name.upper())
                    cmd = 'hostname'
                    res = raas_connection.ssh_command_sync(server, cmd, preset)
                    message = "Test connection to %s: %s" % (preset.cluster_name, res.strip())
                    log.info(message)
                    self.report({'INFO'}, message)
                else:
                    message = "Test connection to %s skipped: preset is disabled" % preset.cluster_name
                    log.info(message)
                    self.report({'INFO'}, message)

        except Exception as e:
            import traceback
            traceback.print_exc()
            log.exception("Problem with %s", self.bl_label)

            self.report({'ERROR'}, "Problem with %s: %s: %s" %
                        (self.bl_label, e.__class__, e))

        log.info("'%s' finished", self.bl_label)
        self.report({'INFO'}, "'%s' finished" % (self.bl_label))
        return {"FINISHED"}


class RaasPreferences(AddonPreferences):
    bl_idname = ADDON_NAME

    error_message: StringProperty(
        name='Error Message',
        default='',
        options={'HIDDEN', 'SKIP_SAVE'}
    )  # type: ignore

    ok_message: StringProperty(
        name='Message',
        default='',
        options={'HIDDEN', 'SKIP_SAVE'}
    )  # type: ignore

    show_ssh_gen: BoolProperty(
        default=False
    )  # type: ignore

    #     name='RaaS Server',
    #     default=''

    raas_username: StringProperty(
        name='Username',
        description='Username to access the server',
        default=''
    )  # type: ignore

    raas_password: StringProperty(
        name='Password',
        description='Password to access the server',
        default='',
        subtype='PASSWORD'
    )  # type: ignore

    ## Adding new clusters
    cluster_presets: bpy.props.CollectionProperty(type=ClusterPresets)

    raas_working_dir: StringProperty(
        name='Project Dir',
        description='The PROJECT data storage is a central storage for projects/users data',
        default=''
    )  # type: ignore

    raas_pid_name: StringProperty(
        name='Project ID',
        description='Project identifier, e.g. OPEN-XX-XX, DD-XX-XX',
        default=''
    )  # type: ignore

    raas_pid_queue: StringProperty(
        name='Project Queue',
        description='The queue for running the job on the cluster, e.g. qcpu, qgpu',
        default='qcpu'
    )  # type: ignore

    raas_pid_dir: StringProperty(
        name='Project Dir',
        description='The PROJECT data storage is a central storage for projects/users data',
        default=''
    )  # type: ignore

    #############################################################

    raas_job_storage_path: StringProperty(
        name='Local Storage Path',
        description='Path where to store job files',
        subtype='DIR_PATH',
        default=tempfile.gettempdir()
    )  # type: ignore

    dependencies_installed: BoolProperty(
        default=False
    )  # type: ignore

    #     name='Use Paramiko',
    #     default=True

    #     name='SSH Library',

    #     name='Key Passphrase',
    #     default='',
    #     subtype='PASSWORD'

    #     name='Private Key Path',
    #     description='Private Key Path',
    #     subtype='FILE_PATH',
    #     default=''

    raas_gen_private_key_path: StringProperty(
        name='Gen. Private Key Path',
        description='Gen. Private Key Path',
        subtype='FILE_PATH',
        default=''
    )  # type: ignore

    raas_gen_public_key_path: StringProperty(
        name='Gen. Public Key Path',
        description='Gen. Public Key Path',
        subtype='FILE_PATH',
        default=''
    )  # type: ignore

    raas_scripts_repository: StringProperty(
        name='Repository',
        default='https://github.com/SCEBE-Technicians/blender-hpc.git'
    )  # type: ignore

    raas_scripts_repository_branch: StringProperty(
        name='Branch',
        default='main'
    )  # type: ignore

    raas_blender_link: StringProperty(
        name='Link',
        default='https://mirrors.dotsrc.org/blender/release/Blender5.1/blender-5.1.2-linux-x64.tar.xz'
    )  # type: ignore

    raas_scripts_installed: BoolProperty(
        default=False
    )  # type: ignore

    #     default=False

    #     name='Project ID',
    #     default=''

    raas_gen_username: StringProperty(
        name='Username',
        default=''
    )  # type: ignore

    raas_gen_password: StringProperty(
        name='Key Passphrase',
        default='',
        subtype='PASSWORD'
    )  # type: ignore

    def check_valid_settings(self, cl, type='NONE'):
        if cl.raas_ssh_library == 'ASYNCSSH' or cl.raas_ssh_library == 'PARAMIKO':
            if len(cl.raas_da_username) == 0:
                show_message_box(
                    message='Username is not set in preferences', icon='ERROR')
                return False

            if not cl.raas_da_use_password and len(raas_connection.get_preset_private_key_file(cl)) == 0:
                show_message_box(
                    message='Private Key File is not set in preferences', icon='ERROR')
                return False

        if not self.raas_scripts_installed and type != 'PROJECT_DIR' and type != 'INSTALL_SCRIPTS' and type != 'INSTALL_BLENDER':
            show_message_box(
                message='Scripts are not installed', icon='ERROR')
            return False

        if len(self.raas_scripts_repository) == 0 or len(self.raas_scripts_repository_branch) == 0:
            show_message_box(
                message='Git repository is not set in preferences', icon='ERROR')
            return False

            #     show_message_box(
        #         message='Blender is not installed', icon='ERROR')

        if len(self.raas_blender_link) == 0:
            show_message_box(
                message='Link to Blender is not set in preferences', icon='ERROR')
            return False

        if not self.dependencies_installed:
            show_message_box(
                message='Dependencies are not installed', icon='ERROR')
            return False

        if not self.raas_job_storage_path and type != 'PROJECT_DIR' and type != 'INSTALL_SCRIPTS' and type != 'INSTALL_BLENDER':
            show_message_box(
                message='Local Storage Path is not set in preferences', icon='ERROR')
            return False

        return True

    def check_valid_settings_gen(self, type='NONE'):
        if not self.dependencies_installed:
            show_message_box(
                message='Dependencies are not installed', icon='ERROR')
            return False

        #     show_message_box(
        #         message='Project ID is not set in the generate SSH keys section', icon='ERROR')

        if len(self.raas_gen_username) == 0:
            show_message_box(
                message='Username is not set in the generate SSH keys section', icon='ERROR')
            return False

        if len(self.raas_gen_public_key_path) == 0 and type != 'GENERATE':
            show_message_box(
                message='Public Key File is not set in the generate SSH keys section', icon='ERROR')
            return False

        if len(self.raas_gen_private_key_path) == 0 and type != 'GENERATE':
            show_message_box(
                message='Private Key File is not set in the generate SSH keys section', icon='ERROR')
            return False

        if len(self.raas_gen_password) == 0:
            show_message_box(
                message='Key Passphrase is not set in the generate SSH keys section', icon='ERROR')
            return False

        return True

    def reset_messages(self):
        self.ok_message = ''
        self.error_message = ''

    def draw(self, context):
        layout = self.layout

        box = layout.box()

        raas_pid = box.split(**factor(1.0), align=True)
        pid_box = raas_pid.row(align=True)
        pid_box.label(text='Cluster settings:')

        raas_pid = box.split(**factor(1.0), align=True)
        pid_box = raas_pid.row(align=True)
        pid_box.operator("pref.newcluster", icon="ADD")

        for idx, preset in enumerate(self.cluster_presets):
            if preset.working_dir == '':
                preset.is_enabled = False
            box_row = box.box()
            raas_pid = box_row.split(**factor(1.0), align=True)
            pid_box = raas_pid.column(align=True)
            pid_box.prop(preset, "cluster_name")
            pid_box.prop(preset, "partition_name")
            job_type_row = pid_box.row(align=True)
            job_type_row.enabled = preset.cluster_name != 'ENUCC'
            job_type_row.prop(preset, "job_type")

            raas_pid = box_row.split(**factor(1.0), align=True)
            pid_box = raas_pid.column(align=True)
            pid_box.prop(preset, "raas_da_username")

            rep_split = box_row.split(**factor(0.25), align=True)
            rep_split.label(text='Use Password:')
            rep_box1 = rep_split.row(align=True)
            rep_box = rep_box1.row(align=True)
            rep_box.prop(preset, 'raas_da_use_password', text='')

            if preset.raas_da_use_password:
                pid_box.prop(preset, "raas_da_password")
            else:
                pid_box.prop(preset, "raas_private_key_path")
                pid_box.prop(preset, "raas_private_key_password")

            raas_pid = box_row.split(**factor(1.0), align=True)
            pid_box = raas_pid.column(align=True)
            pid_box.prop(preset, "raas_ssh_library")

            raas_pid = box_row.split(**factor(1.0), align=True)
            pid_box = raas_pid.column(align=True)
            pid_box.prop(preset, "working_dir", text='Dir')
            pid_box.prop(preset, "is_enabled")
            pid_box.operator("pref.removecluster", icon="CANCEL").index = idx

        if len(self.cluster_presets) > 0:
            raas_pid = box.split(**factor(1.0), align=True)
            pid_box = raas_pid.column(align=True)
            pid_box.operator(RAAS_OT_find_working_dir.bl_idname, icon="CONSOLE")
            pid_box.operator(RAAS_OT_test_connection.bl_idname, icon="CONSOLE")

        box = layout.box()

        raas_box = box.column()
        path_split = raas_box.split(**factor(0.25), align=True)
        path_split.label(text='Local Storage Path:')
        path_box = path_split.row(align=True)
        path_box.prop(self, 'raas_job_storage_path', text='')
        props = path_box.operator(
            'raas.explore_file_path', text='', icon='DISK_DRIVE')
        props.path = self.raas_job_storage_path

        boxD = layout.box()
        boxD.label(text='Blender dependencies:')

        dependencies_installed = preferences().dependencies_installed
        if not dependencies_installed:
            boxD.label(text='Dependencies are not installed', icon='ERROR')

        if not dependencies_installed:
            boxD.operator(RAAS_OT_install_dependencies.bl_idname,
                          icon="CONSOLE")
        else:
            boxD.operator(RAAS_OT_update_dependencies.bl_idname,
                          icon="CONSOLE")

        box = layout.box()

        boxG = box.box()
        boxG.label(text='Install scripts and Blender:')
        rep_split = boxG.split(**factor(0.25), align=True)
        rep_split.label(text='Git Repository (Scripts):')
        rep_box1 = rep_split.row(align=True)
        rep_box = rep_box1.row(align=True)
        rep_box.prop(self, 'raas_scripts_repository', text='')
        rep_box = rep_box1.row(align=True)
        rep_box.prop(self, 'raas_scripts_repository_branch', text='')

        rep_split = boxG.split(**factor(0.25), align=True)
        rep_split.label(text='Link (Blender):')
        rep_box1 = rep_split.row(align=True)
        rep_box = rep_box1.row(align=True)
        rep_box.prop(self, 'raas_blender_link', text='')

        rep_split = boxG.split(**factor(0.25), align=True)
        rep_split.label(text='Manual Installation / Scripts allready installed:')
        rep_box1 = rep_split.row(align=True)
        rep_box = rep_box1.row(align=True)
        rep_box.prop(self, 'raas_scripts_installed', text='')

        #                     icon="CONSOLE", text="Install scripts on the cluster")
        #                     icon="CONSOLE", text="Update scripts")

        #                     icon="CONSOLE", text="Install Blender on the cluster")
        #                     icon="CONSOLE", text="Update Blender")

        if self.raas_scripts_installed == False:  # or self.raas_blender_installed == False:
            if not self.raas_scripts_installed:
                boxG.label(text='Scripts are not installed', icon='ERROR')

            boxG.operator(RAAS_OT_install_scripts.bl_idname,
                          icon="CONSOLE", text="Install scripts and Blender on the cluster(s)")
        else:
            boxG.operator(RAAS_OT_install_scripts.bl_idname,
                          icon="CONSOLE", text="Update scripts and Blender on the cluster(s)")

        #                     icon="CONSOLE")

        #     #     text='Please wait a minute for the public key to install on all clusters before running Setup.')


def ctx_preferences():
    """Returns bpy.context.preferences in a 2.79-compatible way."""
    try:
        return bpy.context.preferences
    except AttributeError:
        return bpy.context.user_preferences


def preferences() -> RaasPreferences:
    return ctx_preferences().addons[ADDON_NAME].preferences


def get_selected_cluster_preset(context):
    """Return the selected cluster preset or raise a user-facing error."""
    prefs = preferences()
    index = context.scene.raas_cluster_presets_index

    if len(prefs.cluster_presets) == 0:
        raise ValueError("No HPC configuration exists. Add a SCEBE configuration in add-on preferences.")

    if index < 0 or index >= len(prefs.cluster_presets):
        raise ValueError(
            "No valid HPC configuration is selected. Select the SCEBE preset in the blender-hpc panel."
        )

    return prefs.cluster_presets[index]


class RaasAuthValidate(async_loop.AsyncModalOperatorMixin, Operator):
    bl_idname = 'raas_auth.validate'
    bl_label = 'Validate'

    async def async_execute(self, context):

        addon_prefs = preferences()
        addon_prefs.reset_messages()

        try:
            resp = await raas_server.get_token(addon_prefs.raas_username, addon_prefs.raas_password)
        except:
            resp = None

        if resp and len(resp) == 36:
            addon_prefs.ok_message = 'Authentication token is valid.'
        else:
            addon_prefs.error_message = 'Authentication token is not valid!'

        self.quit()


def register():
    """register."""

    bpy.utils.register_class(ClusterPresets)
    bpy.utils.register_class(RaasPreferences)
    bpy.utils.register_class(RaasAuthValidate)
    bpy.utils.register_class(RAAS_OT_install_dependencies)
    bpy.utils.register_class(RAAS_OT_update_dependencies)
    bpy.utils.register_class(RAAS_OT_NewClusterPreset)
    bpy.utils.register_class(RAAS_OT_RemoveClusterPreset)
    bpy.utils.register_class(RAAS_OT_find_working_dir)
    bpy.utils.register_class(RAAS_OT_test_connection)
    bpy.utils.register_class(RAAS_OT_install_scripts)

    try:
        for dependency in python_dependencies:
            import_module(module_name=dependency.module,
                          global_name=dependency.name)

        preferences().dependencies_installed = True
    except ModuleNotFoundError as err:
        log.info("Dependency check failed: %s; checked %s", err, DEPENDENCIES_PATH)
        preferences().dependencies_installed = False

    return


def unregister():
    """unregister."""

    bpy.utils.unregister_class(ClusterPresets)
    bpy.utils.unregister_class(RaasAuthValidate)
    bpy.utils.unregister_class(RaasPreferences)
    bpy.utils.unregister_class(RAAS_OT_install_dependencies)
    bpy.utils.unregister_class(RAAS_OT_update_dependencies)
    bpy.utils.unregister_class(RAAS_OT_NewClusterPreset)
    bpy.utils.unregister_class(RAAS_OT_RemoveClusterPreset)
    bpy.utils.unregister_class(RAAS_OT_find_working_dir)
    bpy.utils.unregister_class(RAAS_OT_test_connection)
    bpy.utils.unregister_class(RAAS_OT_install_scripts)

    return
