DialogueFramework -- Dialogue Tree Reference
=============================================

FOLDER LAYOUT
  NPC_<id>\*.json  - dedicated to exactly one NPC ID. Leave NPCIDs
                     empty in these files -- it's inferred from the
                     folder name automatically. This is the folder to
                     use for almost everything: copy NPC_9999, rename
                     it to match your NPC's real ID, edit the json.
  Shared\*.json    - for one tree deliberately covering MULTIPLE NPCs.
                     NPCIDs must be set explicitly here (list every ID
                     that should use this tree).

  If a file sits in a NPC_<id> folder but its own NPCIDs (if set)
  doesn't include that id, a warning is logged on server start -- this
  usually means you copy/pasted a file into a new folder and forgot to
  update something, or just forgot to clear NPCIDs entirely.

  After every server start, check LoadLog.txt in this same folder -- it
  lists exactly what loaded, and exactly which files/NPC IDs (if any)
  failed and were skipped, with the reason why. A conflict or bad file
  never stops the server from starting -- it just means that one NPC
  falls back to no custom dialogue until you fix it.

Files are loaded on server start (restart required after editing).

DialogueTree fields:
  ID              - your own identifier for this tree, for logging only
  NPCIDs          - array of Quest NPC IDs (from your QuestNPC_X.json
                    'ID' field). Leave empty in a NPC_<id> folder to
                    use that folder's id automatically. Required
                    (non-empty) in Shared\.
  RootNodeID      - which node ID in Nodes[] is shown first
  GreetingVoiceLineIDs - array of voice line IDs, one picked at random
                    when the conversation opens
  FarewellVoiceLineIDs - same, played when the player picks a response
                    with ActionType END_CONVERSATION
                  - your own text for the live quest-detail step's
                    responses. EVERY entry shows as its own button (not
                    a random pick) -- these are tone variants meant to
                    appear together. Leave any of these empty to fall
                    back to a plain default instead.
                  - spoken prompt when a quest lets the player pick
                    one of several rewards. ONE is picked at random
                    (it is a line of dialogue, not a set of buttons).
                    Empty falls back to a plain default.
  Stages          - array of extra quest-locked trees for this NPC,
                    each { RequiredQuestID, RootNodeID, Nodes }. Once the
                    player has COMPLETED RequiredQuestID, that whole tree
                    replaces the base one -- its own nodes and root, a
                    clean conversation for that stage of the story. Add
                    as many as you like; the highest completed quest
                    wins. Each stage's node IDs are separate from the
                    base tree and every other stage. Empty = only the
                    base tree is ever used.
  Nodes           - array of DialogueNode

DialogueNode fields:
  ID              - referenced by Responses[].NextNodeID
  Type            - STANDARD (normal authored node), QUEST_LIST or
                    QUEST_DETAIL (both are built live by the mod, you
                    never author these two yourself)
  SpeakerText     - text shown for this line
  VoiceLineIDs    - array of voice line IDs, one picked at random
  Responses       - array of DialogueResponse

DialogueResponse fields:
  Text            - button text shown to the player
  NextNodeID      - which node to show next. -1 ends the conversation
  RequiredQuestID - optional, -1 for no gating. Set to only show this
                    response if that quest ID is complete/active
  ActionType      - NONE (just go to NextNodeID), SHOW_QUEST_LIST
                    (opens live quest list), ACCEPT_QUEST /
                    DECLINE_QUEST (only meaningful inside a QUEST_DETAIL
                    step), END_CONVERSATION (plays a farewell line and
                    closes)

QuestListTexts      - what the NPC says above their live quest list.
                    ONE is picked at random per visit, so a handful of
                    phrasings stops a busy NPC sounding scripted.
                    Empty falls back to built-in wording.
NoQuestsTexts       - what the NPC says when they have nothing available
                    right now, also one at random.
                    NoQuestsBackTexts / NoQuestsLeaveTexts are
                    the buttons offered with it -- every entry is its own
                    button. Back returns to RootNodeID, Leave ends the
                    conversation. Leave all three empty and the player
                    still gets a plain Back button, never a dead end.
NoQuestsVoiceLineIDs - voice lines for that step, one picked at random.

Wording that follows the player's progress:
  A quest can carry its own QuestListTexts and NoQuestsTexts in
  QuestText\*.json. Both are chosen the same way -- the mod uses the
  HIGHEST-numbered quest of this NPC's the player has COMPLETED that
  fills that field, so a chain reads as 'furthest along' with no extra
  setup: an NPC greets a newcomer one way and a veteran another, and
  their 'nothing left' line can point at whoever gives the next quest.
  Both fall back to the tree's own arrays, then to built-in wording.

Per-quest button text:
  Accept / decline / turn-in wording can be set PER QUEST in
  $profile:\DialogFramework\QuestText\*.json, so each quest can read
  in its own voice. Anything not set there falls back to this tree's
  Quest*Texts arrays, then to plain built-in wording.

Voice line IDs:
  A VoiceLineID of "Example_Greeting_1" expects a CfgSoundSets entry
  named "DialogueFW_Example_Greeting_1_SoundSet" to exist -- defined in
  the separate DialogueFramework_SoundSets addon, alongside the actual
  .ogg file. See that addon's own README for how to add your own.
  If a VoiceLineID has no matching SoundSet, that line just plays with
  no audio -- it will not error or break the conversation.

Validation on load (reported in LoadLog.txt, never fatal):
  - A NextNodeID that doesn't match any node in the file (usually a typo)
  - Two nodes in the same file sharing the same ID
  - A RootNodeID that doesn't match any node at all
  These don't stop the server or break other NPCs -- the affected branch
  just won't be reachable until fixed. Check LoadLog.txt after every restart.

See docs/DIALOGUE_TREE_GUIDE.md in the mod's repository for the full
reference, including guidance on building large branching trees.
