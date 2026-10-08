DialogueFramework -- Translations
=============================================

Your dialogue trees stay exactly as they are. Translations live here as
separate overlay files, one folder per language:

  Localization\german\MyTrader.json
  Localization\russian\MyTrader.json

Folder names must be one of:
  english, czech, german, russian, polish, hungarian, italian,
  spanish, french, chinese, japanese, portuguese, chinesesimp

Each player automatically gets the translation matching their DayZ
language, and can pick a different one from the settings button in the
corner of the conversation window. Anything you haven't translated falls back to the
original wording in the tree file -- never to a blank line.

File format:
  {
    "ConfigVersion": 1,
    "Language": "german",
    "Trees": [
      {
        "TreeID": 9999,
        "TreeFile": "npc_9999/dialogue.json",
        "Entries": [
          { "Key": "node.1.SpeakerText", "Text": "Na, wen haben wir denn da?" },
          { "Key": "node.1.Responses.0", "Text": "Ich suche Arbeit." }
        ]
      }
    ],
    "Quests": [
      {
        "QuestID": 1,
        "Entries": [
          { "Key": "quest.AcceptTexts.0", "Text": "Ich mache es." }
        ]
      }
    ]
  }

TreeFile is the tree's path relative to the Dialogues folder, lowercase,
with forward slashes. It is matched first; TreeID is the fallback, so
renaming a tree file only costs you the translations of trees that share
an ID with another tree.

Key formats:
  node.<nodeID>.SpeakerText          the line the character speaks
  node.<nodeID>.SpeakerLines.<i>     one of the node's alternate lines
  node.<nodeID>.Responses.<i>        one of the node's response buttons
  stage.<s>.node.<nodeID>....        the same, inside story stage <s>
  tree.<Field>.<i>                   one entry of a tree-level text list
                                     (QuestListTexts, NoQuestsTexts,
                                     NoQuestsBackTexts, NoQuestsLeaveTexts,
                                     QuestListBackTexts, OfferBackTexts,
                                     InProgressBackTexts, TurnInBackTexts,
                                     ReputationTiers)
  quest.<Field>.<i>                  one entry of a QuestText list
  quest.RewardSelectText             that quest's reward prompt

Indexes are zero-based and count entries as written in the source file,
not as shown to the player. Reordering a list in the tree file means the
translations for that list need reordering too -- DialogueForge does this
for you, which is the easiest way to keep these files honest.

The mod's own wording (Reward:, Confirm, Cancel, the built-in fallback
response lines) is already translated into all supported languages and
needs nothing from you.
