import pytest
from pydantic import ValidationError
from backend.app.models import Stats,Move,MoveOutput,SpriteSpec
from backend.app.sprites import example_spec,Renderer
from .conftest import move

@pytest.mark.parametrize('changes',[{'power':0},{'category':'status'},{'sleep_chance':20,'poison_chance':20},{'healing_percent':20},{'accuracy':0},{'power':151},{'power':True},{'power':'80'},{'unknown':1},{'name':' '}])
def test_invalid_moves(changes):
    with pytest.raises(ValidationError): Move.model_validate({**move().model_dump(),**changes})

@pytest.mark.parametrize('changes',[{'hp':True},{'hp':'80'},{'hp':256},{'hp':0},{'speed':201},{'hp':255,'attack':190,'defense':230},{'iv':0}])
def test_stats(changes):
    data=dict(hp=80,attack=80,defense=80,special_attack=80,special_defense=80,speed=80)
    with pytest.raises(ValidationError): Stats.model_validate({**data,**changes})

@pytest.mark.parametrize('key',['power','accuracy','sleep_chance','healing_percent'])
def test_every_move_field_required(key):
    data=move().model_dump();data.pop(key)
    with pytest.raises(ValidationError): Move.model_validate(data)

def test_noop_duplicate_types_and_no_damage():
    with pytest.raises(ValidationError): move(category='status',power=0)
    with pytest.raises(ValidationError): MoveOutput(types=['fire','fire'],moves=[move()]*4)
    with pytest.raises(ValidationError): MoveOutput(types=['fire'],moves=[move(category='status',power=0,sleep_chance=1)]*4)
    with pytest.raises(ValidationError): MoveOutput(types=['fire'],moves=[move()]*3)

def test_sprite_schema_and_regions():
    renderer=Renderer();data=example_spec().model_dump()
    for change in [{'canvas':[32,64]},{'pose':'back'},{'schema_version':'2'}]:
        with pytest.raises(ValidationError): SpriteSpec.model_validate({**data,**change})
    for regions in [[{'part':'ear_tips','color':'accent'}],[{'part':'head','color':'base'}]*2]:
        with pytest.raises(ValueError): renderer.render(SpriteSpec.model_validate({**data,'regions':regions}))
    data['palette_rules']['base']='red'
    with pytest.raises(ValidationError): SpriteSpec.model_validate(data)
