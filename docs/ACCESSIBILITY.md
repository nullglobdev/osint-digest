# Accessibility in OSINT Digest 1.2

The Windows desktop interface has been rebuilt with standard Qt controls, rounded navy panels, and accessibility features targeting the Revised Section 508 software requirements. This is an implementation and test record, not a completed Accessibility Conformance Report or a claim of full Section 508 conformance. End-to-end assistive-technology testing remains required.

## Use the accessibility controls

- **Theme:** choose Dark, Light, or Windows at the top of the app. Windows uses platform styling. Active Windows contrast themes override the custom themes, including while the app is running. Platform rendering can change the rounded appearance.
- **Text size:** choose 100%, 125%, 150%, 175%, or 200%. The app also uses Windows DPI scaling. Controls wrap and pages scroll; at large sizes the whole workspace can scroll. Preferences save immediately without saving unfinished connection edits.
- **Visible focus:** custom themes use a prominent outline around focused controls. Buttons also use a dashed focus border. Keyboard focus scrolls into view. Source status is written as Enabled or Disabled and does not rely on color.
- **Pause live activity updates:** freezes the displayed log while tasks continue. Uncheck it to catch up. The interface has no pulsing, flashing, or animated radar.
- **Screen-reader metadata:** fields have explicit names and descriptions; labels are associated with controls. Standard widgets expose roles, selection, enabled/read-only/checked states, and values through Qt's platform accessibility integration. Credentials use password fields until Show credentials is selected. Task status requests polite announcements without changing keyboard focus.

## Keyboard reference

| Keys | Action |
|---|---|
| Tab / Shift+Tab | Move forward/backward between controls; text areas do not trap Tab |
| Space | Activate a focused button or checkbox; enable/disable a selected source row |
| Arrow keys | Navigate tabs, lists, tables, model choices, and numeric values |
| Alt+Down | Open a model/provider dropdown |
| Ctrl+1 / Ctrl+2 / Ctrl+3 / Ctrl+4 | Dashboard / Connection / Sources / Previews |
| Ctrl+S | Save connection and source changes |
| Ctrl+Plus / Ctrl+Minus / Ctrl+0 | Increase / decrease / reset text size |
| F1 | Open scrollable keyboard and accessibility help |
| Escape | Cancel a dialog and return to the workspace |
| Ctrl+A / Ctrl+C | Select/copy text from the focused log or preview |

The taskbar and system tray keep their Windows behavior. The tray menu can reopen the app, stop automatic checks, or exit after a task. Opening the executable again restores its existing window.

## Automated and visual checks

The test suite checks normal and muted text, accent text, error text, selected button text, control boundaries, and focus outlines in both custom themes. Text pairs meet at least 4.5:1; control and focus boundaries against their surrounding surfaces meet at least 3:1. These token checks do not substitute for measuring every rendered state.

Widget tests check accessible names/roles, password and disabled states, Tab navigation, section shortcuts, source toggling by keyboard, focus scrolling in a 640×480 window at 200% text, non-compounding text enlargement, contrast-theme override behavior, and pausing the log. Existing tests cover encrypted settings, provider isolation, worker actions, sources, and background checks. Rendered previews are inspected for both themes and large text. Packaged startup checks include the native accessibility interface for the API key field.

## Manual validation still required

Before claiming Section 508 conformance, complete and record these checks on the supported Windows versions:

1. Use Narrator and NVDA with the installed application. Check each field's name, role, value, state, selected model, source-table headers/cells, preview text, and error/task announcements. Confirm hidden credentials are not spoken as plaintext.
2. Complete setup, model selection, source add/edit/reorder, preview reading, and background/restore/exit using only a keyboard. Check focus return from each dialog and the tray; confirm there are no traps.
3. Test actual Windows contrast themes, system font preferences, 100–200% app text size, and multiple Windows DPI settings. Confirm every input, popup, checkbox mark, focus state, and validation message remains visible and operable.
4. Review resizing, scrolling, popup placement, and focus visibility across supported screen sizes. Check live announcements with an actual screen reader while a task finishes.
5. Review all applicable Revised 508/WCAG criteria, documentation/support requirements, and generated content with an accessibility evaluator; record results and unresolved issues in an ACR if procurement requires one.

The implementation targets keyboard access, contrast and text resizing, predictable focus, labeled controls, error identification, assistive-technology interoperability, and platform preferences. Relevant references: [Revised Section 508 Standards](https://www.access-board.gov/ict/), [Qt accessibility](https://doc.qt.io/qt-6/accessible.html), and [Qt announcement events](https://doc.qt.io/qt-6/qaccessibleannouncementevent.html).
