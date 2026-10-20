import { isConcordProtocol } from '@/common/cognitionProtocols';
import {
  SessionsWithCognitionProtocols,
  SessionWithCognitionProtocols
} from '@/types/oxp.type';
import { mockSessionsWithCognitiveObservability } from './sessionsWithCognitiveObservability';
import { mockSessionCognitionProtocols } from './sessionCognitionProtocols';

// The sre-triage application: an orchestrator and five specialists, all running
// on the same model.
const SRE_TRIAGE_AGENTS = [
  'sre_lead',
  'telemetry',
  'backend',
  'db',
  'comms',
  'verifier'
];
const SRE_TRIAGE_LLM = 'vertex_ai/gemini-2.5-flash';

// The usage of a session includes the usage of its protocols, so it cannot be
// lower than what the per-session Cognition protocol mock reports for them. For the sessions
// where the cognitive observability mock is lower, the usage is overridden here
// (the protocols' usage plus the usage of the agents' own work).
const SESSION_USAGE_OVERRIDES: Record<
  string,
  Partial<Pick<SessionWithCognitionProtocols, 'tokens' | 'cost' | 'duration'>>
> = {
  // ACCORD (8,340 tokens, $0.0412) + CONCORD (18,840 tokens, $0.0987)
  '4493f565-d069-47ec-9a6c-5df6dc8f31b7': {
    tokens: 36400,
    cost: 0.417,
    duration: 78200
  },
  // CONCORD (32,200 tokens, $0.1734)
  '41114179-2600-4073-a51d-0150651f2ae8': { tokens: 41800, cost: 0.479 }
};

// The sessions of the cognitive observability mock, each with its Cognition protocol
// status taken from the per-session Cognition protocol mock, so that both views stay
// consistent. Sessions without an entry in the Cognition protocol mock have no Cognition protocol.
const toSessionWithCognitionProtocols = (
  session: (typeof mockSessionsWithCognitiveObservability.sessions)[number]
): SessionWithCognitionProtocols => {
  const protocols = mockSessionCognitionProtocols[session.sessionId]?.protocols ?? [];
  const concord = protocols.find(isConcordProtocol);
  const scores = concord?.outcome?.agentScores ?? [];

  // The worst-off agent is only known when every agent has a score.
  const worstOffSatisfaction =
    scores.length > 0 &&
    scores.every((agent) => typeof agent.score === 'number')
      ? Math.min(...scores.map((agent) => agent.score as number))
      : null;

  return {
    sessionId: session.sessionId,
    timestamp: session.timestamp,
    agents: SRE_TRIAGE_AGENTS,
    llms: [SRE_TRIAGE_LLM],
    tokens: session.tokens,
    status: session.status,
    cost: session.cost,
    duration: session.duration,
    ...SESSION_USAGE_OVERRIDES[session.sessionId],
    cognitiveObservabilityMetrics: session.cognitiveObservabilityMetrics,
    cognitiveFailures: session.cognitiveFailures,
    cognitionProtocols: protocols.map(({ protocol, enabled, activated }) => ({
      protocol,
      enabled,
      activated
    })),
    concord:
      concord && concord.activated
        ? {
            terminalState:
              concord.compliance?.completion?.terminalState ?? null,
            worstOffSatisfaction
          }
        : null
  };
};

export const mockSessionsWithCognitionProtocols: SessionsWithCognitionProtocols = {
  sessions: mockSessionsWithCognitiveObservability.sessions.map(
    toSessionWithCognitionProtocols
  )
};
