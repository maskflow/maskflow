from maskflow_gateway.streaming import SSEDecoder, SSEEvent, format_sse


def test_decoder_yields_complete_events_only() -> None:
    d = SSEDecoder()
    assert d.feed("data: hello\n\ndata: wor") == [SSEEvent(data="hello")]
    assert d.feed("ld\n\n") == [SSEEvent(data="world")]


def test_decoder_captures_event_name_and_multiline_data() -> None:
    d = SSEDecoder()
    events = d.feed("event: ping\ndata: a\ndata: b\n\n")
    assert events == [SSEEvent(data="a\nb", event="ping")]


def test_decoder_handles_crlf_and_comments() -> None:
    d = SSEDecoder()
    events = d.feed(": comment\r\ndata: x\r\n\r\n")
    assert events == [SSEEvent(data="x")]


def test_flush_emits_unterminated_trailing_block() -> None:
    d = SSEDecoder()
    assert d.feed("data: [DONE]") == []
    assert d.flush() == [SSEEvent(data="[DONE]")]


def test_split_at_every_char_reassembles_same_events() -> None:
    stream = "event: a\ndata: 1\n\nevent: b\ndata: 2\n\ndata: 3\n\n"
    expected = [
        SSEEvent(data="1", event="a"),
        SSEEvent(data="2", event="b"),
        SSEEvent(data="3"),
    ]
    for cut in range(1, len(stream)):
        d = SSEDecoder()
        got = d.feed(stream[:cut]) + d.feed(stream[cut:]) + d.flush()
        assert got == expected, cut


def test_format_sse_round_trips_through_decoder() -> None:
    wire = format_sse('{"x":1}', event="delta")
    assert SSEDecoder().feed(wire) == [SSEEvent(data='{"x":1}', event="delta")]
