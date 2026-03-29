/**
 * Strip XML artifacts that LLMs (especially Gemini) sometimes emit as raw text
 * instead of using the structured tool-calling API.
 *
 * Applied at render time so both streamed and persisted messages are clean.
 */

const XML_ARTIFACT_PATTERNS = [
  // Thinking / reasoning tags
  /<thinking>[\s\S]*?<\/thinking>/g,
  /<antml_thinking>[\s\S]*?<\/antml_thinking>/g,
  // Legacy function call XML
  /<function_calls>[\s\S]*?<\/function_calls>/g,
  /<invoke\b[^>]*>[\s\S]*?<\/invoke>/g,
  // Gemini-style tool call/result XML
  /<tool_call>[\s\S]*?<\/tool_call>/g,
  /<tool_calls>[\s\S]*?<\/tool_calls>/g,
  /<tool_results>[\s\S]*?<\/tool_results>/g,
  /<tool_result>[\s\S]*?<\/tool_result>/g,
  /<tool_response>[\s\S]*?<\/tool_response>/g,
]

// Matches an unclosed opening tag at the end of the string that could be the
// start of an artifact (e.g. "<tool_call" or "<tool_call>{..."). During
// streaming, the closing tag hasn't arrived yet — hide the partial artifact.
const PARTIAL_TAG_PATTERN =
  /<(?:thinking|antml_thinking|function_calls|invoke|tool_call|tool_calls|tool_results|tool_result|tool_response)\b[^]*$/

/**
 * Remove LLM XML artifacts from text content.
 * Safe to call on partial (streaming) content — unclosed artifact tags at
 * the end of the string are also stripped.
 */
export function sanitizeLLMContent(text: string): string {
  // Strip fully closed artifact blocks
  for (const pattern of XML_ARTIFACT_PATTERNS) {
    text = text.replace(pattern, '')
  }
  // Strip unclosed artifact tag at end (streaming edge case)
  text = text.replace(PARTIAL_TAG_PATTERN, '')
  // Collapse excessive blank lines left behind
  text = text.replace(/\n{3,}/g, '\n\n')
  return text.trim()
}
