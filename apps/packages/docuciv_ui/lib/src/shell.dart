import 'package:flutter/material.dart';

import 'logo.dart';
import 'tokens.dart';

class DocuCivDestination {
  const DocuCivDestination({
    required this.label,
    required this.icon,
    required this.selectedIcon,
    required this.page,
  });

  final String label;
  final IconData icon;
  final IconData selectedIcon;
  final Widget page;
}

/// Navigation adaptative: barre d'onglets en bas sur mobile, rail latéral au-delà de
/// [wideBreakpoint]. Les onglets gardent leur état (IndexedStack).
class DocuCivShell extends StatefulWidget {
  const DocuCivShell({super.key, required this.destinations, this.logoSuffix});

  final List<DocuCivDestination> destinations;
  final String? logoSuffix;

  @override
  State<DocuCivShell> createState() => _DocuCivShellState();
}

class _DocuCivShellState extends State<DocuCivShell> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final destinations = widget.destinations;
    final body = IndexedStack(
      index: _index,
      children: [for (final d in destinations) d.page],
    );

    return LayoutBuilder(builder: (context, constraints) {
      if (constraints.maxWidth >= wideBreakpoint) {
        return Scaffold(
          body: SafeArea(
            child: Row(
              children: [
                NavigationRail(
                  extended: constraints.maxWidth >= wideBreakpoint + 360,
                  selectedIndex: _index,
                  onDestinationSelected: (i) => setState(() => _index = i),
                  labelType: constraints.maxWidth >= wideBreakpoint + 360
                      ? NavigationRailLabelType.none
                      : NavigationRailLabelType.all,
                  leading: Padding(
                    padding: const EdgeInsets.symmetric(vertical: Space.md),
                    child: constraints.maxWidth >= wideBreakpoint + 360
                        ? DocuCivLogo(suffix: widget.logoSuffix)
                        : const DocuCivMark(),
                  ),
                  destinations: [
                    for (final d in destinations)
                      NavigationRailDestination(
                        icon: Icon(d.icon),
                        selectedIcon: Icon(d.selectedIcon),
                        label: Text(d.label),
                      ),
                  ],
                ),
                const VerticalDivider(width: 1),
                Expanded(child: body),
              ],
            ),
          ),
        );
      }
      return Scaffold(
        appBar: AppBar(
          title: DocuCivLogo(size: 32, suffix: widget.logoSuffix),
          toolbarHeight: 56,
        ),
        body: body,
        bottomNavigationBar: NavigationBar(
          selectedIndex: _index,
          onDestinationSelected: (i) => setState(() => _index = i),
          destinations: [
            for (final d in destinations)
              NavigationDestination(
                icon: Icon(d.icon),
                selectedIcon: Icon(d.selectedIcon),
                label: d.label,
              ),
          ],
        ),
      );
    });
  }
}
