"""Versioned mask catalog, compatibility validation, and deterministic compositing."""
import hashlib
import io
import itertools
import json
from pathlib import Path
from PIL import Image
from .models import SpriteSpec

ASSETS = Path(__file__).parent / 'assets' / 'sprites' / 'v1'
ROLES = ('base','highlight','accent','shadow','outline')
MATRIX = {
 'fox_large_round': {'ears':['none','paired_tall_triangles'], 'tail':['none','single_fluffy_zigzag'], 'limbs':['short_paws'], 'wings':['none','paired_small_feather'], 'horns':['none','single_forehead_horn']},
 'cat_round': {'ears':['none','paired_tall_triangles','paired_round_ears'], 'tail':['none','single_cat_curve'], 'limbs':['short_paws'], 'wings':['none','paired_small_bat','paired_small_feather'], 'horns':['none','single_forehead_horn']},
 'lizard_round': {'ears':['none','paired_short_fins'], 'tail':['none','single_lizard_taper'], 'limbs':['short_claws'], 'wings':['none','paired_small_bat'], 'horns':['none','single_forehead_horn','paired_small_horns']},
}
PALETTE = dict(max_colors=5,base='#3878C8',highlight='#8CC8F0',accent='#F0C840',shadow='#204878',outline='#282830')

def example_spec(head='fox_large_round', **parts):
    row = MATRIX[head]
    silhouette = dict(body_family='biped',body='compact_torso',head=head,eyes='alert',**{k:v[0] for k,v in row.items()})
    silhouette.update(parts)
    return SpriteSpec.model_validate(dict(schema_version='1',canvas=[64,64],silhouette=silhouette,pose='front_three_quarter',palette_rules=PALETTE,regions=[]))

class Renderer:
    def __init__(self, root=ASSETS):
        self.root = Path(root)
        self.catalog = json.loads((self.root/'catalog.json').read_text())
        if self.catalog['version'] != '1':
            raise ValueError('Unsupported sprite catalog version')
        self.fragments = {}
        for part, asset in self.catalog['parts'].items():
            loaded = []
            for fragment in asset['fragments']:
                masks = {}
                for key, filename in fragment['masks'].items():
                    with Image.open(self.root/part/filename) as im:
                        if im.mode != 'L' or set(im.get_flattened_data()) - {0,255}:
                            raise ValueError(f'{part}: masks must be binary grayscale PNGs')
                        masks[key] = im.copy()
                dims = {m.size for m in masks.values()}
                if len(dims)!=1:
                    raise ValueError(f'{part}: mismatched masks')
                role_sets = {r:{i for i,x in enumerate(masks[r].get_flattened_data()) if x} for r in ROLES}
                occupancy = {i for i,x in enumerate(masks['occupancy'].get_flattened_data()) if x}
                if set.union(*role_sets.values()) != occupancy or sum(map(len,role_sets.values())) != len(occupancy):
                    raise ValueError(f'{part}: role masks must partition occupancy')
                region_sets = [{i for i,x in enumerate(m.get_flattened_data()) if x} for k,m in masks.items() if k.startswith('region:')]
                if any(not s <= role_sets['base'] for s in region_sets) or (region_sets and len(set.union(*region_sets)) != sum(map(len,region_sets))):
                    raise ValueError(f'{part}: regions must be disjoint subsets of base')
                loaded.append((fragment,masks))
            self.fragments[part] = loaded
        required = {'compact_torso','alert','gentle','fierce',*MATRIX}
        for row in MATRIX.values():
            for choices in row.values():
                required.update(set(choices)-{'none'})
        if required != set(self.fragments):
            raise ValueError('Catalog does not contain exactly the required v1 parts')

    def validate(self, spec):
        sil = spec.silhouette.model_dump()
        for slot, choices in MATRIX[sil['head']].items():
            if sil[slot] not in choices:
                raise ValueError(f'{slot} incompatible with {sil["head"]}')
        if sil['horns']=='paired_small_horns' and sil['ears']!='none':
            raise ValueError('Paired horns require no ears')
        selected = [v for k,v in sil.items() if k!='body_family' and v!='none']
        regions = {k[7:] for p in selected for _,masks in self.fragments[p] for k in masks if k.startswith('region:')}
        overrides = [r.part for r in spec.regions]
        if len(set(overrides))!=len(overrides) or set(overrides)-regions:
            raise ValueError('Duplicate or absent region override')
        return selected

    def render(self, spec):
        selected = self.validate(spec)
        palette = {r:tuple(bytes.fromhex(getattr(spec.palette_rules,r)[1:]))+(255,) for r in ROLES}
        overrides = {r.part:r.color for r in spec.regions}
        canvas = Image.new('RGBA',(64,64))
        owners = Image.new('I',(64,64),0)
        fragments = [(f['layer'],i,p,f,m) for p in selected for i,(f,m) in enumerate(self.fragments[p])]
        for _,_,part,fragment,masks in sorted(fragments,key=lambda x:(x[0],x[1])):
            anchor = self.catalog['anchors'][self.catalog['parts'][part]['slot']]
            x,y = (anchor[i]+fragment['mask_offset'][i] for i in (0,1))
            w,h = masks['occupancy'].size
            image = Image.new('RGBA',(w,h))
            for role in ROLES:
                image.paste(palette[role],(0,0,w,h),masks[role])
            for key,mask in masks.items():
                if key.startswith('region:') and key[7:] in overrides:
                    image.paste(palette[overrides[key[7:]]],(0,0,w,h),mask)
            bounds = masks['occupancy'].getbbox()
            if bounds and (x+bounds[0]<4 or y+bounds[1]<4 or x+bounds[2]>60 or y+bounds[3]>60):
                raise ValueError('Part outside four-pixel margin')
            canvas.alpha_composite(image,(x,y))
            owners.paste(selected.index(part)+1,(x,y,x+w,y+h),masks['occupancy'])
        visible = set(owners.get_flattened_data())
        if any(i+1 not in visible for i in range(len(selected))):
            raise ValueError('Selected part fully occluded')
        if canvas.getbbox()[3] != 56:
            raise ValueError('Creature must touch baseline y=55')
        occupied={(x,y) for y in range(64) for x in range(64) if canvas.getpixel((x,y))[3]}
        reached=set();pending=[next(iter(occupied))]
        while pending:
            point=pending.pop()
            if point in reached or point not in occupied: continue
            reached.add(point);x,y=point
            pending.extend([(x-1,y),(x+1,y),(x,y-1),(x,y+1)])
        if reached != occupied:
            raise ValueError('Assembly has disconnected pixels or attachments')
        data = io.BytesIO()
        canvas.save(data,format='PNG')
        key = hashlib.sha256(('1:1:'+spec.model_dump_json()).encode()).hexdigest()
        return key, data.getvalue()

def legal_specs(include_expressions=False):
    for head,row in MATRIX.items():
        keys = list(row)
        for values in itertools.product(*(row[k] for k in keys)):
            parts = dict(zip(keys,values))
            if parts['horns']=='paired_small_horns' and parts['ears']!='none':
                continue
            for eyes in (['alert','gentle','fierce'] if include_expressions else ['alert']):
                yield example_spec(head,eyes=eyes,**parts)
