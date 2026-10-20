/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack, Typography } from '@mui/material';
import {
  COGNITION_METRIC_DEFINITIONS,
  COGNITION_METRIC_SECTIONS,
  CognitionMetricKind,
  OTHER_SECTION_TITLE,
  getMetricLabel
} from '@/common/cognitionMetrics';
import { humanizeLabel } from '@/common/cognitionProtocols';
import { CognitionMetric, CognitionProtocol } from '@/types/oxp.type';
import {
  BulletList,
  MetricRow,
  NO_DATA,
  NotAvailable,
  PassFailTag,
  Reason,
  SimpleTable,
  SubSection,
  YesNoTag,
  formatCount
} from './primitives';

const formatPercent = (value: number): string => `${(value * 100).toFixed(1)}%`;

const formatNumber = (value: number): string =>
  Number.isInteger(value)
    ? value.toLocaleString()
    : value.toLocaleString(undefined, { maximumFractionDigits: 4 });

const isMissing = (value?: number | null): value is null | undefined =>
  value === null || value === undefined || Number.isNaN(value);

const MetricValue = ({
  value,
  kind
}: {
  value?: number | null;
  kind?: CognitionMetricKind;
}) => {
  if (isMissing(value)) return <NotAvailable />;
  switch (kind) {
    case 'boolean':
      return (
        <YesNoTag value={value > 0} yesTone="positive" noTone="negative" />
      );
    case 'pass':
      return <PassFailTag passed={value > 0} />;
    case 'percent':
      return <Typography variant={'body2'}>{formatPercent(value)}</Typography>;
    case 'score':
      return <Typography variant={'body2'}>{value.toFixed(2)}</Typography>;
    case 'count':
      return <Typography variant={'body2'}>{formatCount(value)}</Typography>;
    default:
      return <Typography variant={'body2'}>{formatNumber(value)}</Typography>;
  }
};

const formatCell = (value: unknown): string => {
  if (value === null || value === undefined) return NO_DATA;
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number') return formatNumber(value);
  if (Array.isArray(value)) return value.map(formatCell).join(', ');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

// Table of the structured explanation of a metric. The columns are the keys of
// the rows, in the order they first appear.
const DetailsTable = ({ rows }: { rows: Record<string, unknown>[] }) => {
  const keys = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  return (
    <SimpleTable
      headers={keys.map(humanizeLabel)}
      rows={rows.map((row) => keys.map((key) => formatCell(row[key])))}
    />
  );
};

const MetricItem = ({ metric }: { metric: CognitionMetric }) => {
  const definition = COGNITION_METRIC_DEFINITIONS[metric.name];
  const rows = definition?.detailsRows?.(metric.details) ?? null;

  return (
    <MetricRow
      label={getMetricLabel(metric)}
      description={definition?.description}
    >
      <Stack direction="column" gap="6px" alignItems="flex-start">
        <MetricValue value={metric.value} kind={definition?.kind} />
        {!definition?.isReasoningRedundant?.(metric) && (
          <Reason text={metric.reasoning} />
        )}
        {rows && <DetailsTable rows={rows} />}
      </Stack>
    </MetricRow>
  );
};

// Metrics grouped by section: known sections first, in a fixed order, then the
// others in the order they come.
const groupBySection = (metrics: CognitionMetric[]) => {
  const bySection = new Map<string, CognitionMetric[]>();
  metrics.forEach((metric) =>
    bySection.set(metric.section, [
      ...(bySection.get(metric.section) ?? []),
      metric
    ])
  );
  const known = COGNITION_METRIC_SECTIONS.filter(({ key }) => bySection.has(key)).map(
    ({ key, title }) => ({ title, metrics: bySection.get(key) ?? [] })
  );
  const knownKeys = new Set(COGNITION_METRIC_SECTIONS.map(({ key }) => key));
  const others = [...bySection.entries()]
    .filter(([key]) => !knownKeys.has(key))
    .flatMap(([, items]) => items);
  return others.length > 0
    ? [...known, { title: OTHER_SECTION_TITLE, metrics: others }]
    : known;
};

const labeled = (label: string, items?: string[] | null) =>
  items && items.length > 0 ? (
    <MetricRow label={label}>
      <BulletList items={items} />
    </MetricRow>
  ) : null;

// Who had the protocol and who used it, from the protocol execution report.
const Participation = ({ protocol }: { protocol: CognitionProtocol }) => {
  const rows = [
    protocol.enabledEvidence ? (
      <MetricRow
        key="evidence"
        label="Enabled through"
        description="Where the protocol was found enabled."
      >
        <Typography variant={'body2'}>
          {humanizeLabel(protocol.enabledEvidence)}
        </Typography>
      </MetricRow>
    ) : null,
    labeled('Agents that used it', protocol.agentsActivated),
    labeled('Agents that had it', protocol.agentsEnabled),
    labeled('Skills used', protocol.skillsActivated),
    labeled('Skills available', protocol.skillsEnabled)
  ].filter(Boolean);

  return rows.length > 0 ? (
    <SubSection title="Participation">
      <Stack direction="column" gap="8px">
        {rows}
      </Stack>
    </SubSection>
  ) : null;
};

// Generic view of a protocol: its participation and its metrics, as stored.
export const MetricsView = ({ protocol }: { protocol: CognitionProtocol }) => (
  <>
    <Participation protocol={protocol} />
    {groupBySection(protocol.metrics ?? []).map(({ title, metrics }) => (
      <SubSection key={title} title={title}>
        <Stack direction="column" gap="8px">
          {metrics.map((metric) => (
            <MetricItem key={metric.name} metric={metric} />
          ))}
        </Stack>
      </SubSection>
    ))}
  </>
);

export const hasMetrics = (protocol: CognitionProtocol): boolean =>
  (protocol.metrics?.length ?? 0) > 0;
