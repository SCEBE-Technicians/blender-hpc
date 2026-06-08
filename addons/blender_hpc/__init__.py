# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# (c) IT4Innovations, VSB-TUO

bl_info = {
    "name" : "blender-hpc",
    "author" : "Alexander Hallard",
    "description" : "Rendering-as-a-service for Blender on HPC",
    "blender" : (4, 0, 0),
    "version" : (1, 0, 0),
    "location" : "Addon Preferences panel",
    "wiki_url" : "https://scebe-technicians.github.io/enucc-tutorials/software/blender/",
    "category" : "System",
}

import logging
from pathlib import Path

import bpy

log = logging.getLogger(__name__)


def _setup_file_logging():
    """Write addon logs to Blender's user config directory."""

    logger = logging.getLogger(__package__ or __name__)
    log_path = Path(bpy.utils.user_resource('CONFIG', path="blender-hpc", create=True)) / "blender-hpc.log"
    log_path_str = str(log_path)

    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler) and handler.baseFilename == log_path_str:
            return log_path

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))

    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = True

    return log_path

def register():
    """Late-loads and registers the Blender-dependent submodules."""

    log_path = _setup_file_logging()
    log.info("blender-hpc logging to %s", log_path)

    from . import async_loop
    from . import raas_pref
    from . import raas_render

    async_loop.setup_asyncio_executor()
    async_loop.register()

    raas_pref.register()
    raas_render.register()    

def unregister():
    """unregister."""

    from . import async_loop
    from . import raas_pref
    from . import raas_render
    
    try:
        async_loop.unregister()
        raas_pref.unregister()
        raas_render.unregister() 
    except RuntimeError:
        pass

