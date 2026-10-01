"""Ground truth transcribed from the official type chart, independent row order.

Source: https://sg.portal-pokemon.com/game/type-chart/ (checked 2026-10-01).
Rows are attacking types; columns are defending types. All 324 cells are checked.
"""
import pytest
from backend.app.battle import effectiveness

ORDER='normal grass fire water electric bug flying rock poison ground ice fighting psychic ghost dragon dark steel fairy'.split()
ROWS=[
 [1,1,1,1,1,1,1,.5,1,1,1,1,1,0,1,1,.5,1],
 [1,.5,.5,2,1,.5,.5,2,.5,2,1,1,1,1,.5,1,.5,1],
 [1,2,.5,.5,1,2,1,.5,1,1,2,1,1,1,.5,1,2,1],
 [1,.5,2,.5,1,1,1,2,1,2,1,1,1,1,.5,1,1,1],
 [1,.5,1,2,.5,1,2,1,1,0,1,1,1,1,.5,1,1,1],
 [1,2,.5,1,1,1,.5,1,.5,1,1,.5,2,.5,1,2,.5,.5],
 [1,2,1,1,.5,2,1,.5,1,1,1,2,1,1,1,1,.5,1],
 [1,1,2,1,1,2,2,1,1,.5,2,.5,1,1,1,1,.5,1],
 [1,2,1,1,1,1,1,.5,.5,.5,1,1,1,.5,1,1,0,2],
 [1,.5,2,1,2,.5,0,2,2,1,1,1,1,1,1,1,2,1],
 [1,2,.5,.5,1,1,2,1,1,2,.5,1,1,1,2,1,.5,1],
 [2,1,1,1,1,.5,.5,2,.5,1,2,1,.5,0,1,2,2,.5],
 [1,1,1,1,1,1,1,1,2,1,1,2,.5,1,1,0,.5,1],
 [0,1,1,1,1,1,1,1,1,1,1,1,2,2,1,.5,1,1],
 [1,1,1,1,1,1,1,1,1,1,1,1,1,1,2,1,.5,0],
 [1,1,1,1,1,1,1,1,1,1,1,.5,2,2,1,.5,1,.5],
 [1,1,.5,.5,.5,1,1,2,1,1,2,1,1,1,1,1,.5,2],
 [1,1,.5,1,1,1,1,1,.5,1,1,2,1,1,2,2,.5,1],
]

@pytest.mark.parametrize('attacker,defender,value',[(a,d,ROWS[i][j]) for i,a in enumerate(ORDER) for j,d in enumerate(ORDER)])
def test_official_chart_cell(attacker,defender,value):
    assert effectiveness(attacker,[defender])==value
