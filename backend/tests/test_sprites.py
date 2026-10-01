import io
import pytest
from PIL import Image
from backend.app.sprites import Renderer,legal_specs,example_spec
from backend.app.models import SpriteSpec

@pytest.mark.parametrize('spec',list(legal_specs(include_expressions=True)))
def test_every_legal_assembly(spec):
    r=Renderer();key,png=r.render(spec);im=Image.open(io.BytesIO(png))
    assert im.mode=='RGBA' and im.size==(64,64)
    x0,y0,x1,y1=im.getbbox();assert x0>=4 and y0>=4 and x1<=60 and y1==56
    assert len({p[:3] for p in im.get_flattened_data() if p[3]})<=5
    assert r.render(spec)==(key,png)

@pytest.mark.parametrize('head,parts',[('fox_large_round',{'wings':'paired_small_bat'}),('cat_round',{'tail':'single_lizard_taper'}),('lizard_round',{'horns':'paired_small_horns','ears':'paired_short_fins'})])
def test_illegal_combinations(head,parts):
    with pytest.raises(ValueError): Renderer().render(example_spec(head,**parts))

def test_example_and_region_override_preserves_outline():
    r=Renderer();s=example_spec('fox_large_round',ears='paired_tall_triangles',tail='single_fluffy_zigzag')
    data=s.model_dump();data['regions']=[{'part':'head','color':'accent'},{'part':'ear_tips','color':'accent'},{'part':'tail_tip','color':'accent'},{'part':'belly','color':'highlight'}]
    a=Image.open(io.BytesIO(r.render(s)[1]));b=Image.open(io.BytesIO(r.render(SpriteSpec.model_validate(data))[1]))
    outline=tuple(bytes.fromhex(s.palette_rules.outline[1:]))+(255,)
    assert all(y==outline for x,y in zip(a.get_flattened_data(),b.get_flattened_data()) if x==outline)
    assert a.tobytes()!=b.tobytes()
