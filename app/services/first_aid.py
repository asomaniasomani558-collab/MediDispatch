"""Bystander first-aid guidance shown in the civilian app.

Plain-language steps following standard lay first-aid practice consistent
with the Ghana Standard Treatment Guidelines' emergency principles. The full
set is embedded in the civilian page so it works with no network.

NOTE FOR DEPLOYMENT: content must be signed off by the MoH / Ghana
Ambulance Service clinical lead before go-live (see README).
"""

GENERAL_STEPS = [
    "Make sure YOU are safe first - watch for traffic, fire, electricity or water.",
    "Call 112 now if you have not. Stay on the line and follow their instructions.",
    "Keep the person still and calm. Do not give food or drink.",
    "Stay with them until help arrives. Keep this page open so we can find you.",
]

FIRST_AID = {
    "accident": [
        "Switch on hazard lights / warn traffic. Do not stand in the road.",
        "Do NOT move the person unless there is fire or other immediate danger.",
        "If they are bleeding, press firmly on the wound with a clean cloth.",
        "Keep their head and neck still. Talk to them and keep them warm.",
    ],
    "bleeding": [
        "Press firmly and directly on the wound with a clean cloth or your hand (use a bag or gloves if you can).",
        "Keep pressing - do not lift to check. Add more cloth on top if blood soaks through.",
        "If an arm or leg is bleeding heavily, raise it if it is not broken.",
        "Lay the person down and keep them warm.",
    ],
    "breathing": [
        "Help them sit upright, leaning slightly forward.",
        "Loosen tight clothing around the neck and chest.",
        "If they have their own inhaler or medicine, help them use it.",
        "If they stop breathing, start CPR: push hard and fast in the centre of the chest.",
    ],
    "unconscious": [
        "Tap their shoulders and shout. Check if they are breathing (look, listen, feel for 10 seconds).",
        "Breathing: roll them onto their side (recovery position) with head tilted back.",
        "NOT breathing: start CPR - push hard and fast in the centre of the chest, 100-120 per minute.",
        "Keep going until help arrives or they start breathing.",
    ],
    "chest_pain": [
        "Sit them down and keep them calm and still.",
        "Loosen tight clothing.",
        "If they have their own heart medicine, help them take it.",
        "If they collapse and stop breathing, start CPR.",
    ],
    "seizure": [
        "Move hard or sharp objects away. Put something soft under their head.",
        "Do NOT hold them down and do NOT put anything in their mouth.",
        "Note the time the seizure started.",
        "When the shaking stops, roll them onto their side.",
    ],
    "burns": [
        "Stop the burning - move away from the heat source.",
        "Cool the burn under clean running water for 20 minutes.",
        "Remove rings, watches or tight clothing near the burn - not if stuck to the skin.",
        "Cover loosely with clean cling film or a clean cloth. Do NOT apply oil, toothpaste or butter.",
    ],
    "childbirth": [
        "Help the mother lie down or sit in a comfortable position on a clean surface.",
        "Wash your hands. Have clean cloths ready.",
        "Do NOT pull the baby. Support the baby's head as it comes out.",
        "Dry the baby and place it on the mother's chest. Keep both warm. Do not cut the cord.",
    ],
    "poisoning": [
        "Find out what was taken, how much and when. Keep the container.",
        "Do NOT make them vomit.",
        "If chemicals are on the skin, rinse with plenty of clean water.",
        "If they become unconscious and are breathing, place them on their side.",
    ],
    "snakebite": [
        "Move away from the snake. Do not try to catch or kill it.",
        "Keep the person calm and still. Keep the bitten limb still and at heart level.",
        "Remove rings, watches and tight items near the bite.",
        "Do NOT cut, suck the wound, or tie a tight tourniquet.",
    ],
    "drowning": [
        "Get them out of the water only if it is safe for you.",
        "Check breathing. If NOT breathing, give 5 rescue breaths then start CPR.",
        "If breathing, place them on their side and keep them warm.",
    ],
    "other": [
        "Check if they are awake and breathing.",
        "Keep them comfortable and do not move them unless they are in danger.",
        "Watch for any changes and tell the ambulance crew.",
    ],
}


def steps_for(situation: str) -> list[str]:
    return FIRST_AID.get(situation, FIRST_AID["other"])
