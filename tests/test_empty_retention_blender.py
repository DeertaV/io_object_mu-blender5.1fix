"""All source transform nodes survive import; auxiliary visibility is cosmetic."""
import sys
from pathlib import Path
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import io_object_mu_blender51 as addon
addon.register()
from io_object_mu_blender51.mu import Mu, MuObject, MuTransform, MuTagLayer, MuColliderSphere
from io_object_mu_blender51.import_mu import import_mu
from io_object_mu_blender51.utils.import_assets import set_auxiliary_visibility
from io_object_mu_blender51.model import realize_model_instance

def node(name, position):
    obj = MuObject(name)
    obj.transform = MuTransform()
    obj.transform.name = name
    obj.transform.localPosition = position
    obj.transform.localRotation = (1, 0, 0, 0)
    obj.transform.localScale = (1, 1, 1)
    obj.tag_and_layer = MuTagLayer()
    obj.tag_and_layer.tag, obj.tag_and_layer.layer = 'Untagged', 0
    return obj

root = node('root', (0, 0, 0))
parent = node('hierarchy', (1, 2, 3))
unnamed = node('', (4, 5, 6))
named = node('unused named leaf', (7, 8, 9))
collider_node = node('old collider transform', (10, 11, 12))
collider_node.collider = MuColliderSphere(False)
collider_node.collider.radius, collider_node.collider.center = 1, (0, 0, 0)
root.children = [parent, collider_node]
parent.children = [unnamed, named]
mu = Mu()
mu.name, mu.obj, mu.materials, mu.textures = 'empty retention', root, [], []
path = Path(__file__).resolve().parent / 'artifacts/empty-retention.mu'
path.parent.mkdir(exist_ok=True)
mu.write(str(path))
scene = bpy.context.scene
collection = bpy.data.collections.new('complete source transforms')
scene.collection.children.link(collection)
imported, parsed = import_mu(collection, str(path), True, False)
objects = list(collection.objects)
assert len(objects) == 5 and all(o.type == 'EMPTY' for o in objects)
assert all(o.empty_display_size <= 0.00011 and not o.hide_viewport for o in objects), [(o.name, o.empty_display_size, o.hide_viewport) for o in objects]
assert all(o.muproperties.collider == 'MU_COL_NONE' for o in objects)
source_nodes = [parsed.obj] + parsed.obj.children + parsed.obj.children[0].children
assert all(hasattr(n, 'bobj') for n in source_nodes)
assert source_nodes[-2].bobj.parent == source_nodes[1].bobj
bpy.context.view_layer.update()
matrices = {o: o.matrix_world.copy() for o in objects}
for obj in objects:
    set_auxiliary_visibility(obj, True)
    assert obj.empty_display_size > 0
    set_auxiliary_visibility(obj, False)
    assert obj.empty_display_size <= 0.00011
bpy.context.view_layer.update()
assert all(o.matrix_world == matrices[o] for o in objects)

# Realizing one part retains the complete hierarchy and independent visibility.
instance = bpy.data.objects.new('one part', None)
scene.collection.objects.link(instance)
instance.instance_type, instance.instance_collection = 'COLLECTION', collection
instance['ksp_part_root'] = True
clone = realize_model_instance(instance, scene.collection)
copies = list(clone.children_recursive)
assert len(copies) == 5
set_auxiliary_visibility(copies[-1], True)
assert all(o.empty_display_size <= 0.00011 for o in objects)
assert instance.instance_collection == collection
print('EMPTY_RETENTION_TEST_PASS')
