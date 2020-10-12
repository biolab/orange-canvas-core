import glob
import os
import pickle

from PyQt5.QtCore import QSettings

from orangecanvas import config
from ..scheme import Scheme, SchemeNode, SchemeLink, BaseSchemeAnnotation


class Pickler(pickle.Pickler):
    def __init__(self, file, document):
        super().__init__(file)
        self.document = document

    def persistent_id(self, obj):
        if isinstance(obj, Scheme):
            return 'scheme'
        elif isinstance(obj, SchemeNode) and obj in self.document.cleanNodes():
            return "SchemeNode_" + str(self.document.cleanNodes().index(obj))
        elif isinstance(obj, SchemeLink) and obj in self.document.cleanLinks():
            return "SchemeLink_" + str(self.document.cleanLinks().index(obj))
        elif isinstance(obj, BaseSchemeAnnotation) and obj in self.document.cleanAnnotations():
            return "BaseSchemeAnnotation_" + str(self.document.cleanAnnotations().index(obj))
        else:
            return None


class Unpickler(pickle.Unpickler):
    def __init__(self, file, scheme):
        super().__init__(file)
        self.scheme = scheme

    def persistent_load(self, pid: str):
        if pid == 'scheme':
            return self.scheme
        elif pid.startswith('SchemeNode_'):
            node_index = int(pid.split('_')[1])
            return self.scheme.nodes[node_index]
        elif pid.startswith('SchemeLink_'):
            link_index = int(pid.split('_')[1])
            return self.scheme.links[link_index]
        elif pid.startswith('BaseSchemeAnnotation_'):
            annotation_index = int(pid.split('_')[1])
            return self.scheme.annotations[annotation_index]
        else:
            raise pickle.UnpicklingError("Unsupported persistent object")


def scratch_swp_base_name():
    filename = 'scratch.swp.p'
    dirname = os.path.join(config.data_dir(), 'scratch-crashes')
    os.makedirs(dirname, exist_ok=True)
    swpname = os.path.join(dirname, filename)
    return swpname


canvas_scratch_name_memo = {}


def swp_name(canvas):
    document = canvas.current_document()
    if document.path():
        filename = os.path.basename(document.path())
        dirname = os.path.dirname(document.path())
        return os.path.join(dirname, '.' + filename + ".swp.p")
    # else it's a scratch workflow

    if not QSettings().value('startup/load-crashed-workflows', True, type=bool):
        return None

    global canvas_scratch_name_memo
    if canvas in canvas_scratch_name_memo:
        return canvas_scratch_name_memo[canvas]

    swpname = scratch_swp_base_name()

    i = 0
    while os.path.exists(swpname + '.' + str(i)):
        i += 1
    swpname += '.' + str(i)

    canvas_scratch_name_memo[canvas] = swpname

    return swpname


def register_loaded_swp(canvas, swpname):
    canvas_scratch_name_memo[canvas] = swpname


def glob_scratch_swps():
    swpname = scratch_swp_base_name()
    return glob.glob(swpname + ".*")
