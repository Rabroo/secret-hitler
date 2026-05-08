Test
    - A player enacts fascist policy

    - If 3 fascist policies are in, if that changes votes for chancellor
        - it does, players are more likely to vote nein.

    - If the president gives the chancellor a fascist and a liberal policy,
        -the chancellor selects a liberal policy 
            - how it affects trust of the president to the chancellor
        - the chancellor selects a fascist policy
           - how it affects trust of the president to the chancellor 
                -if president is liberal then chancellor predicted role instantly goes to ~ -1

    - if someone enacts 2 fascist policies
        - how it affects other players' trust in them
            - other players are more likely to vote nein for them in the future, and trust them less in general.

    - fascist and liberal in gov together, fascist gives 2 fascists to liberal and claim it was one fascist and one liberal
        - based on trust who do people trust more after that, the president or the chancellor?

for each interaction record difference for belief updates for each player - depending on scenarios

how did they update their beliefs based on scenarios - differences in beliefs after scenarios and things that are happening

10 runs in a scenario - way of measuring this

structured way of seeding scenarios

different system prompts for different players - more certain and less certain ones - in the liberals

way of seeing how they update beliefs - use streamlit to have a good barplot of trust levels for each player, and how they change after each action.

Findings from full run 1:
    - Fascists blend in too well, they dont push for fascist policies early enough, and so when they start to it is already L=4 and a singular liberal policy means they lose. They need to be more aggressive. They also don't play with the urgency that they will lose the next turn if 2 liberals are in and they get 1 liberal at all.

Findings in full run 2:

hide everything thats happening and allow someone to play in the game

if the seed has it so the players get given 9 fascist policies in a row for the first 3 rounds, how do they react to that? do they get more sceptical of players who recieve it later? do they count the cards and know there are only 2 left? do they start to distrust the president who is giving them fascist policies? do they start to distrust the chancellor who is receiving them? how does it affect their votes for the chancellor in the future?