/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack, Typography } from '@mui/material';
import { ACCORD_PHASE_ORDER } from '@/common/l9Protocols';
import { L9AccordProtocol } from '@/types/oxp.type';
import { UsageSummaryTable } from './UsageTables';
import {
  BlockTitle,
  BulletList,
  CheckResult,
  MetricRow,
  NotAvailable,
  Reason,
  SimpleTable,
  StatusTag,
  SubSection,
  VerdictResult,
  YesNoTag,
  formatCount
} from './primitives';

const NO_GROUND_TRUTH = 'N/A (no ground truth for this session)';

const Convergence = ({ protocol }: { protocol: L9AccordProtocol }) => {
  const lockedFrame = protocol.convergence?.lockedFrame;
  const rounds = protocol.convergence?.roundsPerPhase ?? [];

  const rank = (phase: string) => {
    const index = ACCORD_PHASE_ORDER.indexOf(phase.toUpperCase());
    return index === -1 ? ACCORD_PHASE_ORDER.length : index;
  };
  const sortedRounds = [...rounds].sort(
    (a, b) => rank(a.phase) - rank(b.phase)
  );

  return (
    <SubSection title="Compliance">
      <Stack direction="column" gap="16px">
        <MetricRow
          label="Locked frame well-formed"
          description="Do we have a locked frame (the JSON-formatted shared glossary) with all the required fields?"
        >
          {lockedFrame ? (
            <CheckResult
              check={{
                passed: lockedFrame.wellFormed,
                failures: lockedFrame.missingFields
              }}
              failuresLabel="Missing fields"
            />
          ) : (
            <NotAvailable />
          )}
        </MetricRow>
        <Stack direction="column" gap="4px">
          <BlockTitle
            title="Rounds to fixed point, per phase"
            description="How many rounds each phase took to reach its fixed point, the state where a further round adds nothing. A phase can also stop earlier, once another round no longer adds enough coverage per token to be worth it. CONVENE closes in a single round."
          />
          {sortedRounds.length === 0 ? (
            <NotAvailable text="No data" />
          ) : (
            <SimpleTable
              compact
              headers={['Phase', 'Rounds']}
              rows={sortedRounds.map((row) => [
                row.phase,
                formatCount(row.rounds)
              ])}
            />
          )}
        </Stack>
      </Stack>
    </SubSection>
  );
};

const Correctness = ({ protocol }: { protocol: L9AccordProtocol }) => {
  const coverage = protocol.correctness?.issueCoverage;
  const missed = coverage?.missedIssues ?? [];
  const definitions = protocol.correctness?.definitionsFromAllAgents;
  const missingDefinitions = definitions?.issuesMissingDefinition ?? [];

  return (
    <SubSection title="Correctness">
      <Stack direction="column" gap="8px">
        <MetricRow
          label="Issue coverage"
          description="Does the locked frame identify all the issues relevant to the mission, compared against a ground truth of relevant issues?"
        >
          {coverage ? (
            <Stack direction="column" gap="6px" alignItems="flex-start">
              <Typography variant={'body2'}>
                {`${formatCount(coverage.covered)} / ${formatCount(
                  coverage.total
                )} covered`}
              </Typography>
              {missed.length > 0 && (
                <Stack direction="column" gap="2px">
                  <Typography variant={'caption'}>Missed issues:</Typography>
                  <BulletList items={missed} />
                </Stack>
              )}
            </Stack>
          ) : (
            <NotAvailable text={NO_GROUND_TRUTH} />
          )}
        </MetricRow>
        <MetricRow
          label="Definitions from all agents"
          description="Does each issue carry definitions from all agents? The definitions are compared against the agent personas and preferences."
        >
          {definitions ? (
            <Stack direction="column" gap="6px" alignItems="flex-start">
              <YesNoTag value={definitions.complete} noTone="negative" />
              <Reason text={definitions.reason} />
              {missingDefinitions.length > 0 && (
                <Stack direction="column" gap="2px">
                  <Typography variant={'caption'}>
                    Issues missing a definition:
                  </Typography>
                  <BulletList items={missingDefinitions} />
                </Stack>
              )}
            </Stack>
          ) : (
            <NotAvailable />
          )}
        </MetricRow>
      </Stack>
    </SubSection>
  );
};

const Cost = ({ protocol }: { protocol: L9AccordProtocol }) => (
  <SubSection
    title="Cost"
    description="Tokens and cost used by ACCORD in this session. The shared glossary also stays in every agent's working context for the rest of the run, which adds cost beyond the init exchange."
  >
    <UsageSummaryTable usage={protocol.cost?.usage} />
  </SubSection>
);

const Benefits = ({
  protocol,
  concordActivated
}: {
  protocol: L9AccordProtocol;
  concordActivated: boolean;
}) => {
  const benefits = protocol.benefits;

  return (
    <SubSection title="Benefits">
      <Stack direction="column" gap="8px">
        <MetricRow
          label="Goal success"
          description="Did the agents reach the expected outcome on the mission?"
        >
          {benefits?.goalSuccess ? (
            benefits.goalSuccess.achieved === null ? (
              <NotAvailable />
            ) : (
              <Stack direction="column" gap="6px" alignItems="flex-start">
                <StatusTag
                  label={benefits.goalSuccess.achieved ? 'Yes' : 'No'}
                  tone={benefits.goalSuccess.achieved ? 'positive' : 'negative'}
                />
                <Reason text={benefits.goalSuccess.reason} />
              </Stack>
            )
          ) : (
            <NotAvailable />
          )}
        </MetricRow>
        <MetricRow
          label="Mutual understanding"
          description="Did the shared glossary help agents understand each other's messages and outcomes?"
        >
          <VerdictResult verdict={benefits?.mutualUnderstanding} />
        </MetricRow>
        {concordActivated && (
          <MetricRow
            label="Intent Contract consumed by CONCORD"
            description="On INTENT-LOCKED, ACCORD hands over the Intent Contract (Roster, Frame, Glossary and Verifiable Objective) to CONCORD. Shown only when CONCORD also ran."
          >
            <YesNoTag value={benefits?.intentContractConsumedByConcord} />
          </MetricRow>
        )}
      </Stack>
    </SubSection>
  );
};

export const AccordDetails = ({
  protocol,
  concordActivated
}: {
  protocol: L9AccordProtocol;
  // The handoff metric is only relevant when CONCORD also ran.
  concordActivated: boolean;
}) => (
  <>
    <Convergence protocol={protocol} />
    <Correctness protocol={protocol} />
    <Cost protocol={protocol} />
    <Benefits protocol={protocol} concordActivated={concordActivated} />
  </>
);
