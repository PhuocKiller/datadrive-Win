/*
 * SPDX-FileCopyrightText: 2026 Tran Huy Phuoc
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#pragma once

#include <QString>

namespace OCC
{

/**
 * Shows in Windows Explorer whether a sync folder is still connected to its account.
 *
 * With virtual files, a folder whose account is signed out cannot fetch its contents, and
 * Explorer then lists its subfolders as empty. Nothing in Explorer said why. This swaps the icon
 * of the navigation pane entry and of the folder itself for an offline variant while the account
 * is not connected, and back once it is.
 */
class SyncFolderShellStatus
{
public:
    /**
     * @param folderPath absolute path of the sync folder
     * @param navigationPaneClsid CLSID of the folder's navigation pane entry, or empty when the
     *        folder has none (for instance after its sync root was unregistered)
     * @param connected whether the account behind the folder is connected
     */
    static void apply(const QString &folderPath, const QString &navigationPaneClsid, bool connected);

    /// Icon resource shown while the account is connected, in the form Explorer expects.
    [[nodiscard]] static QString connectedFolderIcon();

    /// Icon resource shown while the account is not connected.
    [[nodiscard]] static QString offlineIcon();
};

} // namespace OCC
