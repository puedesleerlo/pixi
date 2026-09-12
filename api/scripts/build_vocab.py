"""Hand-drafted symbol vocabulary, historical priors and visual tags for the 44-card corpus.

Writes data/elements.json and data/card_elements.json.  The tables below ARE the source;
edit here and re-run:  api/.venv/bin/python api/scripts/build_vocab.py

Axis order (contract §1), negative = first pole:
  0 active/passive  1 beginning/ending  2 giving/withholding  3 inward/outward
  4 gain/loss       5 willing/compelled 6 certain/uncertain   7 singular/collective
Sources for priors: Waite, *The Pictorial Key to the Tarot* (1911, public domain) — "Waite 1911";
standard Tarot de Marseille readings — "Marseille tradition".
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_EL = ROOT / "data" / "elements.json"
OUT_CE = ROOT / "data" / "card_elements.json"

PARENTS = [
    ("figure", "Figure", "who is depicted: the kind of being that is the card's subject"),
    ("posture", "Posture / gesture", "what the figure's body is doing"),
    ("celestial", "Celestial", "sun, moon and stars in the sky"),
    ("water", "Water", "water in the scene"),
    ("setting", "Setting / architecture", "landscape and built structures"),
    ("animal", "Animal", "animals and animal-bodied creatures"),
    ("vegetation", "Vegetation", "trees, flowers and garlands"),
    ("object", "Object / emblem", "held or placed objects and emblems"),
]

W, M = "Waite 1911", "Marseille tradition"

# id: (parent, label, gloss, prior[8], [(card_id, source, note), ...])
LEAVES = {
    # ---------- figure ----------
    "robed_figure": ("figure", "Robed figure", "an adult in long robes, gown or cloak (priest, monarch, hermit, sibyl)",
        [0.5, 0.0, 0.5, -1.0, 0.0, 0.0, -1.0, -1.0],
        [("smith-05", W, "the Hierophant 'in the full vestment of his office' — established order, doctrine"),
         ("conver-09", M, "L'Hermite's cloak: withdrawal, the elder who keeps counsel")]),
    "nude_figure": ("figure", "Nude figure", "an unclothed human figure",
        [-0.5, -1.0, -2.0, 1.5, -0.5, -1.0, 0.0, 0.0],
        [("smith-17", W, "the Star: 'the figure ... is entirely naked' — truth unveiled, nothing withheld"),
         ("conver-21", M, "Le Monde's dancing nude: openness, the world made plain")]),
    "child_figure": ("figure", "Child", "a child or infant",
        [-1.5, -2.5, -1.0, 1.0, -1.5, -1.0, -0.5, 0.0],
        [("smith-19", W, "the Sun: 'a naked child ... the simplicity and innocence of a new age'"),
         ("conver-19", M, "Le Soleil's twins: beginnings, innocence, fraternity")]),
    "pair_of_figures": ("figure", "Pair of figures", "exactly two figures in relation (lovers, captives, twins, the falling)",
        [0.0, -0.5, -1.0, 0.5, 0.0, 0.0, 0.5, 1.5],
        [("smith-06", W, "the Lovers: 'attraction, love, beauty, trials overcome' — the bond between two"),
         ("smith-15", W, "the Devil: two chained figures — the pair bound together")]),
    "group_of_figures": ("figure", "Group of figures", "three or more figures together",
        [0.0, 0.5, -0.5, 1.5, 0.0, 0.5, 0.0, 2.5],
        [("smith-20", W, "Judgement: the rising 'of all the dead' — the collective called"),
         ("conver-06", M, "L'Amoureux: three figures, the choice made among others")]),
    "angel_winged_figure": ("figure", "Winged figure", "an angel, cupid or other winged human figure",
        [-0.5, -0.5, -2.0, 1.0, -1.5, 0.5, -1.5, 0.5],
        [("smith-14", W, "Temperance: 'a winged angel' pouring the essences of life — mediation, giving"),
         ("smith-20", W, "Judgement: the angel's summons — a change that is not chosen")]),
    "devil_horned_figure": ("figure", "Horned devil", "a horned, winged devil on a pedestal with chained captives",
        [0.5, 0.5, 2.0, -1.0, 1.5, 2.5, 0.5, 0.5],
        [("smith-15", W, "the Devil: 'ravage, violence, vehemence, extraordinary efforts, force, fatality' — bondage"),
         ("conver-15", M, "Le Diable: attachment, compulsion, being held")]),
    "skeleton": ("figure", "Skeleton", "a skeleton or skeletal rider",
        [0.0, 3.0, 0.5, 0.0, 2.0, 2.0, -0.5, 0.0],
        [("smith-13", W, "Death: 'end, mortality, destruction, corruption' — the ending no one negotiates"),
         ("conver-13", M, "XIII unnamed: transformation through an ending")]),
    # ---------- posture ----------
    "seated_figure": ("posture", "Seated figure", "the main figure is enthroned or seated",
        [2.0, 0.0, 0.5, -0.5, 0.0, 0.0, -1.5, -1.0],
        [("smith-04", W, "the Emperor: 'stability, power, protection' — authority that does not move"),
         ("conver-02", M, "La Papesse seated with the book: settled, receptive knowledge")]),
    "walking_figure": ("posture", "Walking figure", "a figure in mid-stride, travelling",
        [-2.0, -2.0, -0.5, 1.5, 0.0, -1.5, 1.5, -1.5],
        [("smith-00", W, "the Fool: 'a prince of the other world on his travels' — setting out"),
         ("conver-00", M, "Le Mat: the wanderer, departure, the unnumbered start")]),
    "inverted_figure": ("posture", "Inverted figure", "a figure hanging upside down",
        [2.5, 0.5, -0.5, -2.0, 1.0, 1.5, 1.0, -1.5],
        [("smith-12", W, "the Hanged Man: 'wisdom, circumspection, trials, sacrifice' — suspension, reversal"),
         ("conver-12", M, "Le Pendu: being held in place, a pause imposed")]),
    "raised_arm": ("posture", "Raised arm", "an arm lifted: blessing, invocation, holding something aloft",
        [-2.0, -1.0, -1.5, 1.5, -0.5, -1.0, -1.0, 0.0],
        [("smith-01", W, "the Magician: 'one hand upraised' drawing down power — will directed outward"),
         ("smith-05", W, "the Hierophant's 'sign of esotericism' — the blessing given")]),
    # ---------- celestial ----------
    "sun": ("celestial", "Sun", "the sun, a sunburst, or a radiant nimbus",
        [-2.0, -1.5, -1.5, 2.0, -2.5, -1.0, -2.5, 0.5],
        [("smith-19", W, "the Sun: 'material happiness, fortunate marriage, contentment'"),
         ("conver-19", M, "Le Soleil: clarity, success, warmth shared")]),
    "moon": ("celestial", "Moon", "the moon, crescent or full",
        [1.5, 0.0, 0.5, -2.0, 0.5, 1.0, 2.5, 0.0],
        [("smith-18", W, "the Moon: 'hidden enemies, danger, calumny, darkness, terror, deception, occult forces'"),
         ("conver-18", M, "La Lune: the uncertain path, dreams, what is not yet visible")]),
    "star": ("celestial", "Star", "one or more stars",
        [0.5, -1.5, -1.5, 0.0, -1.5, -1.0, -1.0, -0.5],
        [("smith-17", W, "the Star: 'hope and bright prospects' — 'the gifts of the spirit'"),
         ("conver-17", M, "L'Étoile: hope, inspiration, calm after the Tower")]),
    # ---------- water ----------
    "water_falling": ("water", "Falling water", "water poured from a vessel or cascading downward",
        [-0.5, 0.5, -2.5, 2.0, 0.0, -0.5, 0.0, 0.0],
        [("smith-17", W, "the Star: 'pouring Water of Life' from two vessels — release, giving freely"),
         ("smith-14", W, "Temperance: the flow 'from chalice to chalice' — measured giving")]),
    "water_pool": ("water", "Pool or river", "still or standing water: pool, lake, river, sea",
        [1.5, 0.0, 0.0, -1.5, 0.0, 0.0, 1.0, 0.0],
        [("smith-18", W, "the Moon: the crayfish rising from the pool — 'the nameless and hideous tendency' below the surface"),
         ("smith-17", W, "the Star: the great pool 'of the waters of life'")]),
    # ---------- setting ----------
    "mountains": ("setting", "Mountains", "mountains or crags in the landscape",
        [1.0, 0.0, 0.5, -0.5, -0.5, 0.5, -0.5, -1.0],
        [("smith-09", W, "the Hermit on the heights — attainment reached alone"),
         ("smith-04", W, "the Emperor's barren mountains: 'the sterile regulation' of power")]),
    "tower": ("setting", "Tower", "a tower or towers",
        [0.5, 2.0, 1.0, 0.0, 2.0, 2.0, 1.5, 0.0],
        [("smith-16", W, "the Tower: 'misery, distress, indigence, adversity, calamity, disgrace, deception, ruin'"),
         ("conver-16", M, "La Maison Dieu: sudden collapse, the structure broken open")]),
    "pillars": ("setting", "Pillars", "columns, posts or uprights framing the figure",
        [1.5, 0.0, 1.0, -1.0, 0.0, 0.5, -1.5, 0.0],
        [("smith-02", W, "the High Priestess between 'the pillars J. and B.' — the threshold of the sanctuary"),
         ("conver-05", M, "Le Pape's two columns: institution, doctrine, the frame of law")]),
    "veil_curtain": ("setting", "Veil or canopy", "a veil, curtain or canopy",
        [1.0, 0.0, 2.0, -2.5, 0.0, 0.0, 1.5, -1.0],
        [("smith-02", W, "the High Priestess: 'secrets, mystery, the future as yet unrevealed' behind the veil"),
         ("smith-11", W, "Justice: the curtain behind the throne — what is not shown")]),
    "wheel": ("setting", "Wheel", "a great wheel",
        [-1.0, 0.0, 0.0, 0.5, -0.5, 2.0, 2.5, 1.0],
        [("smith-10", W, "Wheel of Fortune: 'destiny, fortune, success, elevation, luck, felicity' — turning without our consent"),
         ("conver-10", M, "La Roue de Fortune: the cycle, rise and fall")]),
    # ---------- animal ----------
    "animal_dog": ("animal", "Dog", "a dog, wolf or dog-like animal",
        [-1.0, -0.5, -1.0, 1.0, 0.0, 0.0, 0.5, 1.0],
        [("smith-00", W, "the Fool: the dog 'still bounding' at his side — instinct, companionship"),
         ("smith-18", W, "the Moon: 'the dog and wolf' — 'the fears of the natural mind'")]),
    "animal_lion": ("animal", "Lion", "a lion or lion-bodied creature (sphinx)",
        [-2.0, 0.0, 0.0, 0.5, -1.0, 0.5, -1.0, -0.5],
        [("smith-08", W, "Strength: 'power, energy, action, courage, magnanimity'"),
         ("conver-11", M, "La Force: mastery of instinct, vigour")]),
    "animal_horse": ("animal", "Horse", "a horse",
        [-2.5, -0.5, 0.0, 2.0, -0.5, 0.5, 0.0, 0.0],
        [("smith-13", W, "Death: 'a mysterious horseman moves slowly' — the advance that cannot be stopped"),
         ("conver-07", M, "Le Chariot's two horses: drive, momentum, direction")]),
    "animal_bird": ("animal", "Bird", "a bird or eagle (including heraldic)",
        [-0.5, 0.0, -0.5, 2.0, -0.5, -1.0, -0.5, -0.5],
        [("smith-17", W, "the Star: 'a bird alights' on the tree — the spirit alighting, message from above"),
         ("conver-04", M, "L'Empereur's eagle shield: sovereignty, far sight")]),
    # ---------- vegetation ----------
    "trees": ("vegetation", "Trees", "one or more trees",
        [1.0, -0.5, -0.5, 0.0, -0.5, 0.0, -0.5, 0.0],
        [("smith-06", W, "the Lovers: 'the Tree of Life' and 'the Tree of the Knowledge' — growth and its price"),
         ("smith-12", W, "the Hanged Man: 'the living wood' of the gallows — sacrifice that still grows")]),
    "flowers": ("vegetation", "Flowers", "roses, lilies, sunflowers, irises",
        [-0.5, -2.0, -1.5, 1.0, -1.5, -0.5, -0.5, 0.5],
        [("smith-01", W, "the Magician: 'roses and lilies' — 'the culture of aspiration'"),
         ("smith-19", W, "the Sun: sunflowers over the wall — flourishing")]),
    "wreath_garland": ("vegetation", "Wreath", "a wreath, garland or mandorla of leaves",
        [0.0, 2.5, -1.0, 1.0, -2.5, -1.0, -2.0, 0.5],
        [("smith-21", W, "the World: 'assured success, recompense, voyage, route' — completion"),
         ("smith-08", W, "Strength: the 'chain of flowers' — gentleness that binds")]),
    # ---------- object ----------
    "crown": ("object", "Crown", "a crown, tiara or crowned head",
        [0.5, 0.0, 0.5, 0.0, -1.5, -0.5, -2.0, -1.5],
        [("smith-04", W, "the Emperor: 'the crown ... of executive and realization' — authority"),
         ("conver-05", M, "Le Pape's triple tiara: sanctioned authority")]),
    "wand_staff": ("object", "Wand or staff", "a wand, staff, sceptre or rod",
        [-1.5, -0.5, 0.0, 0.5, -0.5, -1.0, -0.5, -1.0],
        [("smith-01", W, "the Magician's wand: 'skill, diplomacy, address ... will'"),
         ("conver-09", M, "L'Hermite's staff: the support of the solitary way")]),
    "sword": ("object", "Sword or blade", "a sword, knife or scythe blade",
        [-1.0, 0.5, 1.0, 0.5, 0.5, 0.5, -1.5, -0.5],
        [("smith-11", W, "Justice: the sword of decision — 'equity, rightness, probity'"),
         ("conver-13", M, "XIII's scythe: the cut that ends")]),
    "cup": ("object", "Cup or vessel", "a cup, chalice, jug or vessel",
        [0.5, -0.5, -2.0, 0.0, -1.0, -0.5, 0.0, 0.5],
        [("smith-14", W, "Temperance: 'from chalice to chalice' — measured exchange"),
         ("smith-01", W, "the Magician's cup on the table — the receptive instrument")]),
    "scales": ("object", "Scales", "a balance / pair of scales",
        [1.5, 0.0, 0.0, 0.0, 0.0, 0.5, -2.5, 0.5],
        [("smith-11", W, "Justice: 'equity, rightness, probity, executive' — weighed and settled"),
         ("conver-08", M, "La Justice's balance: equilibrium, judgement")]),
    "lantern": ("object", "Lantern", "a lantern or lamp held up",
        [1.0, 0.5, 0.5, -2.5, 0.0, -1.0, -1.0, -2.5],
        [("smith-09", W, "the Hermit: 'where I am, you also may be' — the lamp of the solitary seeker"),
         ("conver-09", M, "L'Hermite's lamp: prudence, search, the inward light")]),
    "trumpet": ("object", "Trumpet", "a trumpet sounded",
        [-2.0, 1.0, -1.0, 2.5, -0.5, 2.0, -1.0, 2.0],
        [("smith-20", W, "Judgement: 'the great angel ... blowing his bannered trumpet' — the summons"),
         ("conver-20", M, "Le Jugement's trumpet: the call, awakening, being called out")]),
    "banner_flag": ("object", "Banner", "a banner, flag or standard",
        [-0.5, -1.0, -1.0, 2.0, -0.5, 0.0, -1.0, 1.0],
        [("smith-19", W, "the Sun: the child's 'red standard' — proclamation of new life"),
         ("smith-13", W, "Death's banner with the Mystic Rose — the sign carried before")]),
    "scroll_book": ("object", "Book or scroll", "an open book or scroll",
        [1.5, 0.0, 1.5, -2.0, 0.0, 0.0, -1.0, -1.5],
        [("smith-02", W, "the High Priestess: 'the scroll ... signifies the Greater Law' — knowledge partly hidden"),
         ("conver-02", M, "La Papesse's open book: study, secrets, what is read alone")]),
    "flames": ("object", "Flames", "fire, flames or a torch",
        [-2.0, 0.5, 0.0, 1.5, 1.0, 1.5, 1.0, 0.0],
        [("smith-16", W, "the Tower: flames of the lightning-struck house"),
         ("smith-06", W, "the Lovers: 'the tree of flame' — passion, the twelve fruits")]),
    "lightning": ("object", "Lightning", "lightning or fire striking from the sky",
        [-2.5, 2.5, 0.0, 2.0, 2.5, 3.0, 2.0, 0.0],
        [("smith-16", W, "the Tower: 'the lightning flash' — sudden, unchosen ending"),
         ("conver-16", M, "La Maison Dieu: the bolt from heaven")]),
    "chariot_vehicle": ("object", "Chariot", "a chariot or car",
        [-2.5, -1.0, 0.0, 2.0, -1.5, -1.5, -1.0, -0.5],
        [("smith-07", W, "the Chariot: 'succour, providence; also war, triumph, presumption, vengeance, trouble'"),
         ("conver-07", M, "Le Chariot: forward drive, victory, willed motion")]),
    "table_altar": ("object", "Table", "a table or altar with implements laid out",
        [1.0, -1.0, -0.5, 0.5, -0.5, -1.0, -1.0, -0.5],
        [("smith-01", W, "the Magician: 'on the table in front ... the four Tarot suits' — the means at hand"),
         ("conver-01", M, "Le Bateleur's table: the trade, craft, what is set out")]),
    "infinity_lemniscate": ("object", "Lemniscate", "a figure-of-eight sign, or a wide hat shaped as one",
        [-0.5, -0.5, -0.5, 0.0, -1.0, -0.5, -1.5, -0.5],
        [("smith-01", W, "the Magician: 'the sign of life ... the endless cord' above the head"),
         ("smith-08", W, "Strength: the lemniscate 'over the head of the woman' — sustained mastery")]),
}

# card_id: [(element_id, salience), ...]  — what is ACTUALLY visible in that specific image
TAGS = {
    # ---------------- Smith 1909 ----------------
    "smith-00": [("walking_figure", .9), ("animal_dog", .6), ("sun", .45), ("mountains", .45), ("wand_staff", .35), ("flowers", .3)],
    "smith-01": [("robed_figure", .8), ("raised_arm", .8), ("wand_staff", .6), ("table_altar", .5), ("flowers", .4), ("cup", .35), ("sword", .3), ("infinity_lemniscate", .3)],
    "smith-02": [("seated_figure", .9), ("pillars", .7), ("veil_curtain", .6), ("robed_figure", .6), ("crown", .5), ("moon", .4), ("scroll_book", .4)],
    "smith-03": [("seated_figure", .9), ("robed_figure", .6), ("crown", .5), ("trees", .5), ("water_falling", .4), ("wand_staff", .35)],
    "smith-04": [("seated_figure", .9), ("crown", .6), ("robed_figure", .6), ("mountains", .5), ("wand_staff", .45)],
    "smith-05": [("seated_figure", .9), ("robed_figure", .7), ("pillars", .6), ("crown", .6), ("pair_of_figures", .5), ("raised_arm", .5), ("wand_staff", .4)],
    "smith-06": [("pair_of_figures", .85), ("nude_figure", .8), ("angel_winged_figure", .8), ("sun", .5), ("trees", .4), ("flames", .3), ("mountains", .3)],
    "smith-07": [("chariot_vehicle", .9), ("crown", .5), ("wand_staff", .45), ("star", .4), ("animal_lion", .35)],
    "smith-08": [("animal_lion", .9), ("robed_figure", .7), ("wreath_garland", .4), ("infinity_lemniscate", .3), ("mountains", .3), ("flowers", .3)],
    "smith-09": [("robed_figure", .8), ("lantern", .8), ("wand_staff", .5), ("mountains", .5), ("raised_arm", .4)],
    "smith-10": [("wheel", .9), ("angel_winged_figure", .4), ("sword", .3), ("scroll_book", .3), ("animal_lion", .25), ("animal_bird", .2)],
    "smith-11": [("seated_figure", .9), ("sword", .7), ("scales", .7), ("robed_figure", .6), ("crown", .5), ("pillars", .5), ("veil_curtain", .4)],
    "smith-12": [("inverted_figure", .95), ("trees", .6), ("sun", .2)],
    "smith-13": [("skeleton", .9), ("animal_horse", .7), ("banner_flag", .6), ("group_of_figures", .5), ("sun", .3), ("tower", .3), ("child_figure", .3), ("water_pool", .25), ("flowers", .25)],
    "smith-14": [("angel_winged_figure", .9), ("cup", .6), ("water_falling", .6), ("water_pool", .45), ("mountains", .4), ("sun", .3), ("flowers", .3)],
    "smith-15": [("devil_horned_figure", .9), ("pair_of_figures", .7), ("nude_figure", .6), ("flames", .3)],
    "smith-16": [("tower", .9), ("lightning", .8), ("flames", .6), ("pair_of_figures", .5), ("crown", .4), ("mountains", .3)],
    "smith-17": [("nude_figure", .9), ("star", .8), ("water_falling", .7), ("water_pool", .5), ("trees", .3), ("cup", .3), ("animal_bird", .25)],  # one knee on land, one foot on the pool
    "smith-18": [("moon", .9), ("tower", .5), ("animal_dog", .6), ("water_pool", .5), ("mountains", .2)],  # winding path into distant hills
    "smith-19": [("sun", .9), ("child_figure", .8), ("animal_horse", .6), ("banner_flag", .5), ("flowers", .5), ("nude_figure", .4)],
    "smith-20": [("angel_winged_figure", .8), ("group_of_figures", .8), ("trumpet", .6), ("nude_figure", .6), ("raised_arm", .5), ("banner_flag", .4), ("water_pool", .3), ("mountains", .3)],
    "smith-21": [("nude_figure", .9), ("wreath_garland", .8), ("wand_staff", .45), ("animal_lion", .2), ("animal_bird", .2), ("angel_winged_figure", .2)],  # two wands, oval wreath with ribbons
    # ---------------- Conver 1760 ----------------
    "conver-00": [("walking_figure", .9), ("animal_dog", .6), ("wand_staff", .5)],
    "conver-01": [("table_altar", .7), ("wand_staff", .6), ("raised_arm", .5), ("cup", .4), ("sword", .3)],
    "conver-02": [("seated_figure", .9), ("scroll_book", .6), ("crown", .6), ("robed_figure", .6), ("veil_curtain", .4)],
    "conver-03": [("seated_figure", .9), ("crown", .6), ("wand_staff", .5), ("robed_figure", .5), ("animal_bird", .4)],
    "conver-04": [("seated_figure", .8), ("crown", .6), ("wand_staff", .5), ("robed_figure", .5), ("animal_bird", .3)],
    "conver-05": [("seated_figure", .8), ("robed_figure", .7), ("crown", .6), ("wand_staff", .5), ("pillars", .5), ("pair_of_figures", .5), ("raised_arm", .4)],
    "conver-06": [("group_of_figures", .85), ("angel_winged_figure", .6), ("sun", .5)],
    "conver-07": [("chariot_vehicle", .9), ("animal_horse", .7), ("crown", .5), ("wand_staff", .4), ("veil_curtain", .3)],
    "conver-08": [("seated_figure", .9), ("sword", .7), ("scales", .7), ("robed_figure", .6), ("crown", .5)],
    "conver-09": [("robed_figure", .8), ("lantern", .8), ("wand_staff", .5), ("walking_figure", .5), ("raised_arm", .4)],
    "conver-10": [("wheel", .9), ("animal_dog", .4), ("animal_lion", .3), ("crown", .3), ("sword", .3)],
    "conver-11": [("animal_lion", .9), ("robed_figure", .7), ("infinity_lemniscate", .3)],
    "conver-12": [("inverted_figure", .95), ("trees", .5), ("pillars", .35)],
    "conver-13": [("skeleton", .95), ("sword", .6), ("crown", .3)],
    "conver-14": [("angel_winged_figure", .9), ("cup", .6), ("water_falling", .6), ("flowers", .2)],
    "conver-15": [("devil_horned_figure", .9), ("pair_of_figures", .7), ("nude_figure", .5), ("flames", .3)],
    "conver-16": [("tower", .9), ("lightning", .7), ("flames", .6), ("pair_of_figures", .5), ("crown", .4), ("sun", .3)],
    "conver-17": [("nude_figure", .9), ("star", .85), ("water_falling", .65), ("water_pool", .45), ("trees", .25), ("cup", .35), ("animal_bird", .2)],  # larger star, both knees down, jugs more prominent
    "conver-18": [("moon", .9), ("tower", .6), ("animal_dog", .55), ("water_pool", .45)],  # two dogs, crayfish, drops; no path
    "conver-19": [("sun", .9), ("pair_of_figures", .8), ("child_figure", .8), ("nude_figure", .4)],
    "conver-20": [("angel_winged_figure", .8), ("group_of_figures", .7), ("trumpet", .6), ("nude_figure", .5), ("banner_flag", .4)],
    "conver-21": [("nude_figure", .9), ("wreath_garland", .85), ("wand_staff", .3), ("animal_lion", .2), ("animal_bird", .2), ("angel_winged_figure", .2)],  # one wand + vial, leafy mandorla
}


def main() -> None:
    elements = []
    for pid, label, gloss in PARENTS:
        kids = [v[3] for v in LEAVES.values() if v[0] == pid]
        prior = [round(sum(k[i] for k in kids) / len(kids), 2) for i in range(8)]
        elements.append({"id": pid, "label": label, "gloss": gloss, "parent_id": None,
                         "historical_prior": prior, "prior_coded_by": "human", "attestations": []})
    for eid, (pid, label, gloss, prior, atts) in LEAVES.items():
        assert len(prior) == 8 and all(-3 <= p <= 3 for p in prior), eid
        elements.append({"id": eid, "label": label, "gloss": gloss, "parent_id": pid,
                         "historical_prior": [float(p) for p in prior], "prior_coded_by": "human",
                         "attestations": [{"card_id": c, "source": s, "note": n} for c, s, n in atts]})
    OUT_EL.write_text(json.dumps(elements, indent=1, ensure_ascii=False) + "\n")

    rows = []
    for cid, tags in TAGS.items():
        for eid, sal in tags:
            assert eid in LEAVES, (cid, eid)
            rows.append({"card_id": cid, "element_id": eid, "visual_salience": float(sal), "tagged_by": "human"})
    OUT_CE.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {OUT_EL} ({len(elements)} elements, {len(LEAVES)} leaves) and {OUT_CE} ({len(rows)} tags over {len(TAGS)} cards)")


if __name__ == "__main__":
    main()
