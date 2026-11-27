# pii-veil for Claude (Chrome extension)

Use claude.ai as normal. Before your message is sent, pii-veil swaps real
names, emails, phone numbers and IDs for realistic fakes. Claude only ever
receives the fakes. When Claude answers, you see the real names again.

## Install (about 1 minute)

1. Download this repo: on GitHub, click **Code → Download ZIP**, then unzip it.
   (Or `git pull` if you already cloned it.)
2. In Chrome, open `chrome://extensions`.
3. Turn on **Developer mode** (top-right switch).
4. Click **Load unpacked** and choose the **`extension`** folder inside `pii-veil`.
5. Open or refresh https://claude.ai. A **🛡 pii-veil ON** badge appears at the bottom right.

After an update (`git pull` or a new ZIP), click the ↻ reload icon on the
pii-veil card in `chrome://extensions`, then refresh claude.ai.

## Use it

- Type or paste your message and press **Enter** or **Send** as usual.
  A short note says how many items were hidden.
- Click the **🛡 badge** to see:
  - **What Claude saw**: the exact masked text that was sent
  - **Hidden in this chat**: each real value → its fake. Click **✕** to forget one item
  - **Always hide**: names the built-in list doesn't know (one per line)
  - an **on/off switch**
- Copying text from Claude's answer gives you the real names.

## Try this

```
Please draft a reply to John Smith (john.smith@acme-logistics.com, +65 9123 4567).
His parcel for order 48213 never arrived and his colleague sarah tan already chased twice.
```

Claude answers about the fake people; you see John Smith and Sarah Tan.
Click the badge and "What Claude saw" to prove the real names never left.

## Limits (prototype)

- **Plain text only.** Images and files are sent as they are; pii-veil shows a warning.
- Unusual names (e.g. "chlyde iza") need to be added to **Always hide**.
- Claude's **draft cards** (e.g. email drafts with *Send via Gmail*) show real names.
  Claude's **Artifacts** panel may still show fake names.
- If you **edit an earlier message**, its edit box shows the fake names (on purpose).
  Any real names you type there are hidden when you click Save or press Enter.
- Real values are restored **on your screen only**. Claude's servers keep the fake version.
- Each chat has its own fakes, so chats can't be linked by fake names. Names you
  found once are still recognised in every chat.
- *Use this version* on a draft card puts the fakes back before saving.
- The draft card may show *Reset changes* / *Use this version* even if you didn't edit it
  (pii-veil swapped the real names in). Both are safe to click.
- The real ↔ fake list is stored only in this browser. "Forget all hidden items" deletes it,
  after which old chats show fake names.
- If claude.ai changes its page design, the extension may need an update.
