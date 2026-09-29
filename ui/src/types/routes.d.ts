/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

interface SideBarProps {
  title: string;
  icon?: React.ReactElement;
  preview?: boolean;
  disabled?: boolean;
  hidden?: boolean;
}

type AppRoute = {
  name: string;
  path: string;
  element: React.ReactElement;
  sideBarProps?: SideBarProps;
  children?: AppRoute[];
};
