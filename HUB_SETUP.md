# Hub chapters (Path of Radiance)

Open **Chapters → Create hub**. Choose a free chapter number, title, activation chapter, dedicated avatar, starter map assets, and the width and height of a new flat grass map. The creator keeps compatible archive resources from the selected chapter while replacing its terrain and clearing its copied units, events, and messages. The avatar must not be deployed in another chapter.

Add a linked chapter, then click the map canvas to place its action tile and return point. Click **Place avatar** to choose the initial spawn tile. Each link offers **Arrive**, which enters the chapter. An optional short description adds **Visit** on the same tile; Visit shows the message and leaves the avatar in the hub. At least one link is required. The canvas uses the same controls as the chapter Build tab, which opens after installation for map decoration. Reopen the creator to edit links, descriptions, or the avatar position. Use chapter 29 for activation after the two-part chapter 28–29.

The setup appends persistent campaign flags and generated events, then installs routing in `main.dol`. The first victory of the activation chapter stores its normal successor and opens the hub. Clearing a selected chapter returns to the hub while `HUB_ACTIVE` is set. Clearing the saved next story chapter advances the saved story position. Chapter 28 and 29 remain one continuous segment. If installation fails after chapter creation, the creator retains a draft for a later retry.

To leave hub mode, put `clr("HUB_ACTIVE")` in the selected chapter's story event before its victory. That victory loads the saved next story chapter. If it *is* the saved next story chapter, it loads that chapter's normal successor. To start another hub period later, a story event can set `HUB_ACTIVE` again; the already-saved story position remains available only until it is resumed.

Hub visits are omitted from the game's forty-entry chapter-clear history. The generated hub script clears the avatar's acted flag after each action and updates the map, allowing repeated moves and actions within the player phase. Set the avatar's Move stat high enough for the travel distance you want per action. Test this behavior in Dolphin with the specific actions your hub offers, especially any custom action or scripted movement.

Changing the names or order of the generated `HUB_*` global flags changes how saves interpret their bits. Keep their registration slots fixed after distributing saves.
