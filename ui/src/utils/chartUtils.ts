/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

export const COLOR_PALETTE = [
  '#3A95FF',
  '#00B98D',
  '#F2643D',
  '#9B6FE8',
  '#1ABC9C',
  '#E6A23C',
  '#C62953',
  '#4ECDC4',
  '#5B8CFF',
  '#D4679A'
];

export const buildColorMap = (groups: { label: string }[]) => {
  const domain: string[] = [];
  const range: string[] = [];
  groups.forEach((g, i) => {
    domain.push(g.label);
    range.push(COLOR_PALETTE[i % COLOR_PALETTE.length]);
  });
  return { domain, range };
};
