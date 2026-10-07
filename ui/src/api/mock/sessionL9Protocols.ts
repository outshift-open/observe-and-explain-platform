import { SessionL9Protocols } from '@/types/oxp.type';

// Mocked L9 protocols per session. Sessions that are not listed have no L9
// protocol at all (empty `protocols` list). Scenarios:
//  - 4493f565: CONCORD (COMMIT) and ACCORD, both activated, with handoff
//  - 41114179: CONCORD ending in BEST_EFFORT with a shortfall
//  - 0e78e3a6: CONCORD expected but not started (missed activation) + ACCORD
//              without ground truth
//  - 65d1c926: CONCORD (COMMIT) with a lot of missing metrics
//  - 5980fc14: ACCORD enabled but not activated
export const mockSessionL9Protocols: Record<string, SessionL9Protocols> = {
  '4493f565-d069-47ec-9a6c-5df6dc8f31b7': {
    sessionId: '4493f565-d069-47ec-9a6c-5df6dc8f31b7',
    protocols: [
      {
        protocol: 'L9-ACCORD',
        displayName: 'L9-ACCORD',
        description:
          'Runs before the task: each agent states what it means by the terms in play, who it is, what it thinks the problem is and what it knows, and ACCORD assembles it all into one shared model. Locking it emits the Intent Contract (Roster, Frame, Glossary and Verifiable Objective). Conflicting definitions are recorded with the agent that holds each, not resolved. It is not one-shot: an agent can raise a scoped update later, for example before a delegation or before final synthesis.',
        enabled: true,
        activated: true,
        activatedAt: 'Init, before first delegation',
        convergence: {
          lockedFrame: { wellFormed: true, missingFields: [] },
          roundsPerPhase: [
            { phase: 'CONVENE', rounds: 1 },
            { phase: 'FRAME', rounds: 2 },
            { phase: 'GROUND', rounds: 3 },
            { phase: 'VERIFY', rounds: 2 },
            { phase: 'LOCK', rounds: 1 }
          ]
        },
        correctness: {
          issueCoverage: {
            covered: 5,
            total: 6,
            missedIssues: ['Customer-facing impact window']
          },
          definitionsFromAllAgents: {
            complete: false,
            reason:
              'Four of five issues carry a definition from every agent. The db agent did not define "error rate".',
            issuesMissingDefinition: ['error rate']
          }
        },
        cost: {
          usage: {
            inputTokens: 4120,
            outputTokens: 1380,
            cacheReadTokens: 2200,
            cacheCreationTokens: 640,
            totalTokens: 8340,
            inputCost: 0.012,
            outputCost: 0.019,
            cacheReadCost: 0.0012,
            cacheCreationCost: 0.009,
            totalCost: 0.0412
          }
        },
        benefits: {
          goalSuccess: {
            achieved: true,
            reason:
              'The remediation matches the expected action: roll back checkout-service to the previous version.'
          },
          mutualUnderstanding: {
            label: 'SATISFACTORY',
            reason:
              'Agents used the glossary definitions of "error rate" and "P99 latency" consistently in later messages.'
          },
          intentContractConsumedByConcord: true
        }
      },
      {
        protocol: 'L9-CONCORD',
        displayName: 'L9-CONCORD',
        description:
          'Runs during the task: reconciles divergent-but-correct preferences into one decision. It does not decide who is right, it looks for the outcome every agent can live with, within a round budget. It ends in COMMIT (every agent clears the satisfaction floor) or BEST_EFFORT (the budget ran out, and the shortfall is reported). It certifies agreement, not correctness.',
        enabled: true,
        activated: true,
        activatedAt: 'Specialists diverged, before run_action',
        expected: {
          expected: true,
          reason:
            'The backend and db specialists reached different conclusions about the cause of the incident.'
        },
        compliance: {
          candidateCompleteness: { passed: true },
          completion: { passed: true, terminalState: 'COMMIT' },
          protocolCompliance: { passed: true, failures: [] }
        },
        correctness: {
          outcomeSatisfaction: {
            label: 'SATISFACTORY',
            reason:
              'Every specialist stated it can stand behind the committed remediation.'
          },
          scoreFairness: {
            label: 'FAIR',
            reason: 'Raw scores match each agent’s stated reasoning.'
          }
        },
        cost: {
          usage: {
            inputTokens: 9210,
            outputTokens: 3050,
            cacheReadTokens: 5400,
            cacheCreationTokens: 1180,
            totalTokens: 18840,
            inputCost: 0.031,
            outputCost: 0.042,
            cacheReadCost: 0.0057,
            cacheCreationCost: 0.02,
            totalCost: 0.0987
          },
          phases: [
            {
              phase: 'pre_concord',
              llmCalls: 2,
              inputTokens: 900,
              outputTokens: 210,
              cacheReadTokens: 0,
              cacheCreationTokens: 300,
              cost: 0.0061
            },
            {
              phase: 'init',
              llmCalls: 3,
              inputTokens: 1400,
              outputTokens: 420,
              cacheReadTokens: 600,
              cacheCreationTokens: 200,
              cost: 0.0112
            },
            {
              phase: 'anchors',
              llmCalls: 3,
              inputTokens: 1500,
              outputTokens: 480,
              cacheReadTokens: 900,
              cacheCreationTokens: 180,
              cost: 0.0139
            },
            {
              phase: 'seeds',
              llmCalls: 4,
              inputTokens: 1800,
              outputTokens: 700,
              cacheReadTokens: 1100,
              cacheCreationTokens: 250,
              cost: 0.0188
            },
            {
              phase: 'scores',
              llmCalls: 6,
              inputTokens: 2600,
              outputTokens: 900,
              cacheReadTokens: 2000,
              cacheCreationTokens: 150,
              cost: 0.0331
            },
            {
              phase: 'commit_and_after',
              llmCalls: 2,
              inputTokens: 1010,
              outputTokens: 340,
              cacheReadTokens: 800,
              cacheCreationTokens: 100,
              cost: 0.0156
            }
          ],
          bounds: [
            { name: 'Rounds', achieved: 3, bound: 6 },
            { name: 'Options generated', achieved: 6, bound: 9 },
            { name: 'Agent evaluations', achieved: 18, bound: 27 },
            { name: 'Model calls', achieved: 20, bound: 40 }
          ]
        },
        outcome: {
          tau: 0.7,
          trajectory: [
            { round: 0, worstAgentScore: 0.31 },
            { round: 1, worstAgentScore: 0.44 },
            { round: 2, worstAgentScore: 0.58 },
            { round: 3, worstAgentScore: 0.72 }
          ],
          agentScores: [
            { agent: 'telemetry', score: 0.84 },
            { agent: 'backend', score: 0.72 },
            { agent: 'db', score: 0.78 }
          ],
          shortfall: null
        }
      }
    ]
  },
  '41114179-2600-4073-a51d-0150651f2ae8': {
    sessionId: '41114179-2600-4073-a51d-0150651f2ae8',
    protocols: [
      {
        protocol: 'L9-CONCORD',
        displayName: 'L9-CONCORD',
        enabled: true,
        activated: true,
        activatedAt: '2026-10-07T08:41:12Z',
        expected: {
          expected: true,
          reason:
            'The backend and db specialists disagreed on the remediation: a rollback versus a database fix.'
        },
        compliance: {
          candidateCompleteness: { passed: true },
          completion: { passed: true, terminalState: 'BEST_EFFORT' },
          protocolCompliance: {
            passed: false,
            failures: ['anchors: missing anchor for agent "db"']
          }
        },
        correctness: {
          outcomeSatisfaction: {
            label: 'MIXED',
            reason:
              'The db specialist accepted the outcome only because its score was lifted, not because it can live with it.'
          },
          scoreFairness: {
            label: 'INSUFFICIENT_DATA',
            reason: 'Scoring rationale was not recorded for two agents.'
          }
        },
        cost: {
          usage: {
            inputTokens: 15200,
            outputTokens: 5100,
            cacheReadTokens: 9800,
            cacheCreationTokens: 2100,
            totalTokens: 32200,
            inputCost: 0.0452,
            outputCost: 0.064,
            cacheReadCost: 0.0112,
            cacheCreationCost: 0.053,
            totalCost: 0.1734
          },
          phases: [
            {
              phase: 'init',
              llmCalls: 3,
              inputTokens: 2100,
              outputTokens: 600,
              cacheReadTokens: 800,
              cacheCreationTokens: 400,
              cost: 0.0181
            },
            {
              phase: 'seeds',
              llmCalls: 5,
              inputTokens: 3900,
              outputTokens: 1300,
              cacheReadTokens: 2200,
              cacheCreationTokens: 600,
              cost: 0.0402
            },
            {
              phase: 'scores',
              llmCalls: 14,
              inputTokens: 9200,
              outputTokens: 3200,
              cacheReadTokens: 6800,
              cacheCreationTokens: 1100,
              cost: 0.1151
            }
          ],
          bounds: [
            { name: 'Rounds', achieved: 6, bound: 6 },
            { name: 'Options generated', achieved: 9, bound: 9 },
            { name: 'Agent evaluations', achieved: 27, bound: 27 },
            { name: 'Model calls', achieved: 22, bound: 40 }
          ]
        },
        outcome: {
          tau: 0.7,
          trajectory: [
            { round: 0, worstAgentScore: 0.22 },
            { round: 1, worstAgentScore: 0.31 },
            { round: 2, worstAgentScore: 0.38 },
            { round: 3, worstAgentScore: 0.42 },
            { round: 4, worstAgentScore: 0.47 },
            { round: 5, worstAgentScore: 0.49 },
            { round: 6, worstAgentScore: 0.51 }
          ],
          agentScores: [
            { agent: 'telemetry', score: 0.77 },
            { agent: 'db', score: 0.51 },
            { agent: 'backend', score: 0.71 }
          ],
          shortfall: { agent: 'db', shortBy: 0.19 }
        }
      }
    ]
  },
  '0e78e3a6-9ec4-46af-8835-0a69360c6c9e': {
    sessionId: '0e78e3a6-9ec4-46af-8835-0a69360c6c9e',
    protocols: [
      {
        protocol: 'L9-ACCORD',
        displayName: 'L9-ACCORD',
        enabled: true,
        activated: true,
        activatedAt: 'Init, before first delegation',
        convergence: {
          lockedFrame: {
            wellFormed: false,
            missingFields: ['scope', 'success_criteria']
          },
          roundsPerPhase: [
            { phase: 'CONVENE', rounds: 1 },
            { phase: 'FRAME', rounds: 4 },
            { phase: 'GROUND', rounds: null },
            { phase: 'VERIFY', rounds: 1 },
            { phase: 'LOCK', rounds: 1 }
          ]
        },
        correctness: {
          // No ground truth for this session.
          issueCoverage: null,
          definitionsFromAllAgents: {
            complete: null,
            reason: 'Agent definitions were not recorded in the trace.'
          }
        },
        cost: {
          usage: {
            inputTokens: 3300,
            outputTokens: 900,
            cacheReadTokens: null,
            cacheCreationTokens: null,
            totalTokens: null,
            inputCost: 0.011,
            outputCost: 0.0105,
            totalCost: 0.0215
          }
        },
        benefits: {
          goalSuccess: null,
          mutualUnderstanding: null,
          intentContractConsumedByConcord: false
        }
      },
      {
        protocol: 'L9-CONCORD',
        displayName: 'L9-CONCORD',
        enabled: true,
        activated: false,
        activatedAt: null,
        expected: {
          expected: true,
          reason:
            'The backend and db specialists reached conflicting conclusions, but no decision protocol ran.'
        }
      }
    ]
  },
  '65d1c926-de00-451f-bdcc-eb38bbe39c3a': {
    sessionId: '65d1c926-de00-451f-bdcc-eb38bbe39c3a',
    protocols: [
      {
        protocol: 'L9-CONCORD',
        displayName: 'L9-CONCORD',
        enabled: true,
        activated: true,
        activatedAt: null,
        expected: null,
        compliance: {
          candidateCompleteness: null,
          completion: { passed: null, terminalState: null },
          protocolCompliance: { passed: true }
        },
        correctness: {
          outcomeSatisfaction: null,
          scoreFairness: { label: 'SOME_NEW_LABEL', reason: null }
        },
        cost: {
          usage: {
            inputTokens: 5200,
            outputTokens: null,
            cacheReadTokens: 0,
            cacheCreationTokens: null,
            totalTokens: null,
            inputCost: 0.0052,
            totalCost: null
          },
          phases: [
            {
              phase: 'init',
              llmCalls: 2,
              inputTokens: 1200,
              outputTokens: null,
              cacheReadTokens: 0,
              cacheCreationTokens: null,
              cost: 0.0084
            },
            {
              phase: 'scores',
              llmCalls: 5,
              inputTokens: 4000,
              outputTokens: 1100,
              cacheReadTokens: 0,
              cacheCreationTokens: null,
              cost: 0.0312
            }
          ],
          bounds: [
            { name: 'Rounds', achieved: 2, bound: null },
            { name: 'Model calls', achieved: null, bound: 40 }
          ]
        },
        outcome: {
          tau: null,
          trajectory: null,
          agentScores: [
            { agent: 'telemetry', score: 0.7 },
            { agent: 'backend', score: null }
          ],
          shortfall: null
        }
      }
    ]
  },
  '5980fc14-3a53-429a-bef7-6d7af89cae8c': {
    sessionId: '5980fc14-3a53-429a-bef7-6d7af89cae8c',
    protocols: [
      {
        protocol: 'L9-ACCORD',
        displayName: 'L9-ACCORD',
        enabled: true,
        activated: false,
        activatedAt: null
      }
    ]
  }
};
