# Hub chapters (Path of Radiance)

Create an added chapter (33–89) with one map phase. Prepare its map and deploy a dedicated character in its player section. Keep that character out of every other chapter's deployment. Remove the copied chapter's old victory event from its script, and take the hub chapter out of the normal story order before configuring it.

Open **Chapters → Hub setup**. Choose the prepared hub, the chapter whose first victory activates it, and the avatar's `PID_` name. Use chapter 29 if activation should occur after the two-part chapter 28–29. Add one destination per line as `chapter, action X, action Y, return X, return Y`. The action tile offers **Arrive**. The return tile is where the avatar appears after completing that destination.

The setup appends persistent campaign flags and generated events, then installs routing in `main.dol`. The first victory of the activation chapter stores its normal successor and opens the hub. Clearing a selected chapter returns to the hub while `HUB_ACTIVE` is set. Clearing the saved next story chapter advances the saved story position. Chapter 28 and 29 remain one continuous segment.

To leave hub mode, put `clr("HUB_ACTIVE")` in the selected chapter's story event before its victory. That victory loads the saved next story chapter. If it *is* the saved next story chapter, it loads that chapter's normal successor. To start another hub period later, a story event can set `HUB_ACTIVE` again; the already-saved story position remains available only until it is resumed.

Hub visits are omitted from the game's forty-entry chapter-clear history. The generated hub script clears the avatar's acted flag after each action and updates the map, allowing repeated moves and actions within the player phase. Set the avatar's Move stat high enough for the travel distance you want per action. Test this behavior in Dolphin with the specific actions your hub offers, especially any custom action or scripted movement.

Changing the names or order of the generated `HUB_*` global flags changes how saves interpret their bits. Keep their registration slots fixed after distributing saves.
