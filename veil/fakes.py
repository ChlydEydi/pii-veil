"""Pools of realistic replacement values.

The cloud AI should see data that *looks* real (so its answers stay just as
good) but belongs to nobody. Names are split by gender so pronouns in the
AI's answer still make sense after we swap the real names back in.

Words that are also common English words (Will, May, Mark, Grace, Bill...)
are deliberately left out of the FAKE pools: when we swap fakes back, a fake
"Will" would collide with the verb "will".
"""

# ---- names the detector recognises (real-world input) -------------------
# Kept small on purpose: this is a proof of concept. A local NER model or a
# small self-hosted LLM (see detect.LocalLLMDetector) replaces this list in a
# real deployment.
KNOWN_FIRST_NAMES_MALE = """
john james robert michael william david richard joseph thomas charles chris
christopher daniel matthew anthony mark donald steven paul andrew joshua kevin
brian george edward ronald timothy jason jeffrey ryan jacob gary nicholas eric
jonathan stephen larry justin scott brandon benjamin samuel frank gregory
raymond alexander patrick jack dennis jerry tyler aaron jose adam henry nathan
peter zachary kyle walter ethan jeremy harold keith christian roger noah gerald
carl terry sean austin arthur lawrence jesse dylan bryan joe jordan billy bruce
albert willie gabriel logan alan juan wayne roy ralph randy eugene vincent
russell elijah louis bobby philip johnny ken kenneth adrian ha hieu minh tuan
wei jun ming hao kumar raj arjun ahmad muhammad ali omar chen lee kim
""".split()

KNOWN_FIRST_NAMES_FEMALE = """
mary patricia jennifer linda elizabeth barbara susan jessica sarah karen lisa
nancy betty margaret sandra ashley kimberly emily donna michelle carol amanda
dorothy melissa deborah stephanie rebecca sharon laura cynthia kathleen amy
angela shirley anna brenda pamela emma nicole helen samantha katherine christine
debra rachel carolyn janet catherine maria heather diane ruth julie olivia
joyce virginia victoria kelly lauren christina joan evelyn judith megan andrea
cheryl hannah jacqueline martha gloria teresa ann sara madison frances kathryn
janice jean abigail alice judy sophia isabella denise amber doris marilyn
danielle beverly charlotte natalie theresa diana brittany lily mei ling hui
yan priya anjali fatimah aisha nur siti jowie
""".split()

# ---- fake replacement pools ---------------------------------------------
FAKE_FIRST_MALE = """
Arlen Bastian Caspar Dorian Emeric Fabian Garrick Hollis Idris Jasper Kellan
Lucian Magnus Nolan Orson Percival Quentin Rowan Silas Tobias Ulric Valen
Wystan Xavian Yorick Zane Anselm Bram Cormac Desmond Evander Fenwick Gideon
Hadrian Ignatius Jarvis Leander Mortimer Niall Osric Phineas Rafferty Soren
Thaddeus Upton Vaughn Wolfe Ambrose Barnaby Cillian
""".split()

FAKE_FIRST_FEMALE = """
Adeline Briony Celeste Delphine Elowen Fenella Giselle Honora Imogen Juniper
Kestrel Liesel Marisol Noemi Ottilie Perpetua Quilla Rosalind Saoirse Tamsin
Ursula Verity Wilhelmina Xanthe Yvaine Zinnia Annika Beatrix Clementine
Damaris Esme Florentine Genevieve Henrietta Isolde Jessamy Leocadia Marguerite
Nerys Oriane Philippa Romilly Seraphina Thomasina Ulla Vivienne Winifred
""".split()

FAKE_LAST = """
Ashworth Blackwood Cresswell Dunmore Ellerby Fairbrook Galloway Hartwell
Ingleby Jessop Kingsley Lockwood Merriweather Northcott Oakhurst Pemberton
Quarrington Ravenscroft Sutherland Thistlewood Underhill Vandermeer Whitlock
Yardley Abernathy Bellingham Carrington Drummond Eastwood Fennimore Grantham
Holloway Iverson Kensington Langford Montague Nettleton Ormsby Prescott
Radcliffe Sterling Templeton Upshaw Wainwright Winterbourne Aldridge Brockhurst
""".split()

FAKE_COMPANIES = """
Brightmoor Calderwood Duskline Emberfield Foxglove Glenhaven Hollowpine
Ironbark Juniperhill Kestrelwood Larkspur Marlowe Nightingale Oakridge
Pinecrest Quillfeather Riverstone Silverbirch Thornbury Umberleigh
""".split()

# Domains under the reserved ".example" TLD (RFC 2606): they look like real
# company domains to the AI but can never belong to a real person.
FAKE_EMAIL_DOMAINS = [c.lower() + ".example" for c in FAKE_COMPANIES]
