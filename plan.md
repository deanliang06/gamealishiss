I want to create a game with this sequence:

You join a lobby with an opposing player (via code). The first player creates the lobby and the second player on a different computer enters this code in. Then, when both click the start button they enter the game.

The game starts off with the prompt "Describe your first pokemon", and a chat box appears (make it a cool background with a pokemon theme in the back). When they submit their entry, they are presented with another set of prompt and submission button but with the text "Describe your second pokemon".

Then, they are placed into battle with ficticious pokemon with ficticious moves and stats that are dependent on how ferocious the prompt was and the typing (same types from pokemon) which would be most likely given prompt. Then, the two players battle it out. 

THAT WAS THE GAMEPLAY NOW THE IMPLMENTATION:

1. I want a react front-end, tailwind for styling, and framer motion for animations, and a FastAPI backend 

2. When the user submits a description of their pokemon, and it obviously sends a backend request. I want it to create the pokemon's stats first from the description(HP, Attack, Defense, Sp. Attack, Sp. Defense, and Speed), via a strutured ChatGPT response conforming to a pydantic class with those ints.

3. Then, I want another structured openai API response to create the pokemon's type and their 4 moves. This class will Most likely look like this: """
class MoveOuput(pydantic...):
    type : string
    moves : List[Move]

class Move(pydantic):
    accuracy: int
    power: int
    type: string
    paralyze_self: bool
    paralyze_other: bool
    sleep_self: bool
    sleep_other: bool
    poison_other: bool
    special: bool
"""

4. Then, I want to create the pokemon sprite. I want you to create a sprite building system [please refine]. Then, given the parameters, we ask the openai for another structured ouput this time in the shape of the parametrs required for the sprite building system. 

We do this for both pokemon and then once the battle starts, we render these items in a normal pokemon-fashion (we have no animation for attacking we just display the attacks with a decrement or increment to the health bar). Stats work the same as they do in pokemon games, and typing effectiveness and non-effectiveness work the same. You can switch pokemon, and once the winner wins, we display text to represent that they won (or that they lost), and we have a button to play again or exit to lobby.