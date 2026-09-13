"""Offline training and delivery-order replay entry point."""
import argparse
import json
from pathlib import Path
from . import RiskEngine, build_training_rows, train
from .features import event_from_mapping, utc


def jsonl(path):
    """Yield nonblank JSON objects from a JSON Lines file.

    Args:
        path: File path to read.

    Yields:
        One decoded JSON object per nonblank line.
    """
    with Path(path).open() as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def main():
    """Run the package command-line interface.

    The ``train`` command builds point-in-time training rows from the data
    folder and writes a model artifact. The ``replay`` command feeds events to
    the online engine in delivery order, writes canonical predictions, and
    saves a restorable snapshot.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['train', 'replay'])
    parser.add_argument('--data', type=Path, default=Path('data'))
    parser.add_argument('--artifact', type=Path, default=Path('outputs/final_model'))
    parser.add_argument('--output', type=Path, default=Path('outputs/replay'))
    parser.add_argument('--max-shipments', type=int, default=10000)
    args = parser.parse_args()
    events = (event_from_mapping(r) for r in jsonl(args.data / 'events.jsonl'))
    if args.command == 'train':
        decisions = ((r['shipment_id'], utc(r['decision_time'])) for r in jsonl(args.data / 'decision_times.jsonl'))
        rows = build_training_rows(events, jsonl(args.data / 'labels.jsonl'), decisions)
        print(json.dumps(train(rows, args.artifact), indent=2))
    else:
        engine = RiskEngine(args.artifact, args.max_shipments)
        args.output.mkdir(parents=True, exist_ok=True)
        with (args.output / 'predictions.jsonl').open('wb') as handle:
            for event in events:
                if engine.ingest(event):
                    handle.write(engine.score(event.shipment_id, event.received_at).to_wire() + b'\n')
        engine.snapshot(args.output / 'snapshot.json')
        print(json.dumps(engine.stats(), indent=2))


if __name__ == '__main__':
    main()
