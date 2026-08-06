package main

import (
	"github.com/wailsapp/wails/v2/pkg/menu"
	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// trayOpenAction returns a MenuItem that shows the main window when clicked.
func trayOpenAction() *menu.MenuItem {
	return &menu.MenuItem{
		Text: "Open Window",
		Action: func(ctx *menu.CallbackContext) {
			runtime.WindowShow(ctx.App)
		},
	}
}

// trayQuitAction returns a MenuItem that quits the application.
func trayQuitAction() *menu.MenuItem {
	return &menu.MenuItem{
		Text: "Quit",
		Action: func(ctx *menu.CallbackContext) {
			runtime.Quit(ctx.App)
		},
	}
}

// appMenu returns the main menu for the application (top bar on macOS, etc.).
func appMenu() *menu.Menu {
	openItem := trayOpenAction()
	quitItem := trayQuitAction()

	return menu.NewMenuFromItems(
		&menu.Menu{
			Title: "octopus-desktop",
			Items: []*menu.MenuItem{
				openItem,
				quitItem,
			},
		},
	)
}
