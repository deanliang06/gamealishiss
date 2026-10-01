import math
import pytest
from backend.app.battle import damage,effectiveness,execute,resolve,CHART
from backend.app.models import Action,TYPES
from .conftest import creature,move,Rolls

def test_stats_hp_and_paralysis():
    c=creature();assert c.max_hp==140 and c.current_hp==140 and c.stat('attack')==85
    c.status='paralysis';assert c.stat('speed')==42
    c.base_stats=c.base_stats.model_copy(update={'speed':1});assert c.stat('speed')==3

@pytest.mark.parametrize('random_percent',[85,100])
@pytest.mark.parametrize('category',['physical','special'])
def test_exact_damage(category,random_percent):
    a=creature(types=['fire'],attack=90,special_attack=70);b=creature(types=['grass','steel'],defense=70,special_defense=90)
    m=move(type='fire',category=category,power=80)
    attack,defense=(95,75) if category=='physical' else (75,95)
    expected=math.floor((22*80*(attack/defense)/50+2)*1.5*4*random_percent/100)
    assert damage(a,b,m,random_percent)==expected

def test_chart_is_complete_and_neutral_default():
    assert set(CHART)==set(TYPES)
    for attacker in TYPES:
        for defender in TYPES:
            assert effectiveness(attacker,[defender]) in (0,.5,1,2)
    assert effectiveness('electric',['ground','water'])==0
    assert effectiveness('ice',['dragon','flying'])==4
    assert effectiveness('fire',['water','dragon'])==.25
    assert effectiveness('ghost',['steel'])==1
    assert effectiveness('fairy',['dark'])==2

def test_immunity_minimum_and_status_damage_zero():
    a,b=creature(),creature(types=['ghost'])
    assert damage(a,b,move(),100)==0
    assert damage(a,b,move(category='status',power=0,sleep_chance=100),100)==0
    assert damage(creature(attack=1),creature(defense=230,attack=1),move(type='bug',power=1),85)>=1
    events=[];execute(a,b,move(poison_chance=100),Rolls(1),events);assert b.status is None and b.current_hp==b.max_hp
    execute(a,b,move(category='status',power=0,poison_chance=100),Rolls(1,1),events);assert b.status=='poison'

def test_accuracy_threshold_and_miss():
    a,b=creature(),creature();events=[]
    execute(a,b,move(accuracy=50,poison_chance=100),Rolls(51),events)
    assert b.current_hp==140 and b.status is None
    execute(a,b,move(accuracy=50,poison_chance=100),Rolls(50,100,100),events)
    assert b.current_hp<140 and b.status=='poison'

def test_sleep_exactly_two_actions():
    a,b=creature(),creature();a.status='sleep';a.sleep_actions=2;events=[]
    execute(a,b,move(),Rolls(),events);assert a.sleep_actions==1 and b.current_hp==140
    execute(a,b,move(),Rolls(),events);assert a.status is None and b.current_hp==140
    execute(a,b,move(),Rolls(1,100),events);assert b.current_hp<140

@pytest.mark.parametrize('roll,acted',[(25,False),(26,True)])
def test_paralysis_threshold(roll,acted):
    a,b=creature(),creature();a.status='paralysis'
    execute(a,b,move(),Rolls(roll,1,100) if acted else Rolls(roll),[])
    assert (b.current_hp<140)==acted

def test_healing_rounds_caps_misses_and_preserves_status():
    a,b=creature(hp=81),creature();a.current_hp=10;a.status='poison'
    heal=move(category='status',power=0,healing_percent=50,accuracy=90)
    execute(a,b,heal,Rolls(91),[]);assert a.current_hp==10
    execute(a,b,heal,Rolls(90),[]);assert a.current_hp==80 and a.status=='poison'
    a.current_hp=140;execute(a,b,heal,Rolls(1),[]);assert a.current_hp==141
    a.current_hp=0;execute(a,b,heal,Rolls(),[]);assert a.current_hp==0

def test_existing_status_not_replaced_and_fainted_target_no_status():
    a,b=creature(),creature();b.status='poison'
    execute(a,b,move(category='status',power=0,sleep_chance=100),Rolls(1,1),[]);assert b.status=='poison'
    b.status=None;b.current_hp=1
    execute(a,b,move(sleep_chance=100),Rolls(1,100),[]);assert b.current_hp==0 and b.status is None

def setup():
    return {'a':[creature('a0'),creature('a1')],'b':[creature('b0'),creature('b1')]},{'a':0,'b':0}

def test_switch_target_and_sleep_preserved():
    teams,active=setup();teams['b'][0].status='sleep';teams['b'][0].sleep_actions=2
    events,order,required,result=resolve(teams,active,{'a':Action(kind='move',index=0),'b':Action(kind='switch',index=1)},Rolls(1,100))
    assert teams['b'][0].current_hp==140 and teams['b'][1].current_hp<140
    assert teams['b'][0].sleep_actions==2 and order==['a'] and not required and result is None

def test_both_switch_no_moves():
    teams,active=setup();resolve(teams,active,{p:Action(kind='switch',index=1) for p in teams},Rolls())
    assert active=={'a':1,'b':1} and all(c.current_hp==140 for team in teams.values() for c in team)

@pytest.mark.parametrize('tie,first',[(0,'a'),(1,'b')])
def test_tie_and_knockout_cancels_original_action(tie,first):
    teams,active=setup();teams['a'][0].current_hp=teams['b'][0].current_hp=1
    events,order,required,result=resolve(teams,active,{p:Action(kind='move',index=0) for p in teams},Rolls(tie,1,100))
    assert order[0]==first and required==[next(p for p in teams if p!=first)] and result is None
    assert any('before acting' in e for e in events)

def test_status_speed_does_not_reorder_turn():
    teams,active=setup();teams['a'][0].base_stats=teams['a'][0].base_stats.model_copy(update={'speed':100})
    teams['a'][0].kit.moves[0]=move(paralysis_chance=100)
    _,order,_,_=resolve(teams,active,{p:Action(kind='move',index=0) for p in teams},Rolls(1,100,1,26,1,100))
    assert order==['a','b'] and teams['b'][0].status=='paralysis'

@pytest.mark.parametrize('reserve_alive,reason',[(True,None),(False,'battle')])
def test_simultaneous_poison_faint_and_draw(reserve_alive,reason):
    teams,active=setup()
    for team in teams.values():
        team[0].status='poison';team[0].current_hp=1
        team[0].kit.moves[0]=move(category='status',power=0,sleep_chance=100,accuracy=1)
        team[1].status='poison';team[1].current_hp=140 if reserve_alive else 0
    _,_,required,result=resolve(teams,active,{p:Action(kind='move',index=0) for p in teams},Rolls(0,100,100))
    assert all(t[0].current_hp==0 for t in teams.values())
    if reason: assert result=={'reason':'battle','winner':None}
    else: assert set(required)=={'a','b'} and all(t[1].current_hp==140 for t in teams.values())

def test_single_team_loss():
    teams,active=setup();teams['a'][0].base_stats=teams['a'][0].base_stats.model_copy(update={'speed':100});teams['b'][0].current_hp=1;teams['b'][1].current_hp=0
    _,_,required,result=resolve(teams,active,{p:Action(kind='move',index=0) for p in teams},Rolls(1,100))
    assert result['winner']=='a' and required==[]
