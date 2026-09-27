"""Create a fresh JavaScript practice project and open the live-model TUI."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.safety import git

ISSUE = "Fix invoice.js: percentage discounts must reduce the subtotal before tax, and shipping must be free when the pre-discount subtotal is at least 100. Preserve item validation, quantity calculations, rounding, and zero-discount behavior. Fix the source only; do not change tests."
SOURCE = """'use strict';

function money(value) {
    return Math.round((value + Number.EPSILON) * 100) / 100;
}

function validatePercent(value, name) {
    if (!Number.isFinite(value) || value < 0 || value > 100) {
        throw new RangeError(name + ' must be between 0 and 100');
    }
}

function subtotalFor(items) {
    if (!Array.isArray(items)) throw new TypeError('Items must be an array');
    return money(items.reduce((sum, item) => {
        if (!item || !Number.isFinite(item.price) || item.price < 0 ||
            !Number.isInteger(item.quantity) || item.quantity <= 0) {
            throw new TypeError('Each item needs a price and positive integer quantity');
        }
        return sum + item.price * item.quantity;
    }, 0));
}

function invoiceTotal(subtotal, discountPercent = 0, taxPercent = 0) {
    if (!Number.isFinite(subtotal) || subtotal < 0) throw new RangeError('Invalid subtotal');
    validatePercent(discountPercent, 'Discount');
    validatePercent(taxPercent, 'Tax');
    const discounted = subtotal * (1 + discountPercent / 100);
    return money(discounted * (1 + taxPercent / 100));
}

function shippingFor(subtotal, threshold = 100, fee = 10) {
    return subtotal > threshold ? 0 : fee;
}

function createInvoice(items, options = {}) {
    const subtotal = subtotalFor(items);
    const discountPercent = options.discountPercent ?? 0;
    const taxPercent = options.taxPercent ?? 0;
    const totalBeforeShipping = invoiceTotal(subtotal, discountPercent, taxPercent);
    const shipping = shippingFor(subtotal);
    return {
        subtotal,
        shipping,
        total: money(totalBeforeShipping + shipping)
    };
}

module.exports = { money, subtotalFor, invoiceTotal, shippingFor, createInvoice };
"""
TESTS = """const test = require('node:test');
const assert = require('node:assert/strict');
const { invoiceTotal, subtotalFor, shippingFor, createInvoice } = require('../invoice.js');
test('discount is subtracted before tax', () => {
    assert.equal(invoiceTotal(100, 20, 10), 88);
});
test('full discount gives zero', () => {
    assert.equal(invoiceTotal(50, 100, 12), 0);
});
test('zero discount preserves subtotal', () => {
    assert.equal(invoiceTotal(100, 0, 0), 100);
});
test('fractional result is rounded', () => {
    assert.equal(invoiceTotal(19.99, 15, 8), 18.35);
});
test('subtotal includes quantities', () => {
    assert.equal(subtotalFor([{price: 25, quantity: 2}, {price: 10, quantity: 3}]), 80);
});
test('empty items have zero subtotal', () => {
    assert.equal(subtotalFor([]), 0);
});
test('invalid quantities are rejected', () => {
    assert.throws(() => subtotalFor([{price: 10, quantity: 0}]), TypeError);
    assert.throws(() => subtotalFor([{price: 10, quantity: 1.5}]), TypeError);
});
test('invalid prices are rejected', () => {
    assert.throws(() => subtotalFor([{price: -1, quantity: 1}]), TypeError);
});
test('invalid discount percentages are rejected', () => {
    assert.throws(() => invoiceTotal(100, 101, 0), RangeError);
});
test('shipping below the threshold costs ten', () => {
    assert.equal(shippingFor(99.99), 10);
});
test('shipping at the threshold is free', () => {
    assert.equal(shippingFor(100), 0);
});
test('shipping above the threshold is free', () => {
    assert.equal(shippingFor(100.01), 0);
});
test('invoice combines discount, tax and free shipping', () => {
    assert.deepEqual(createInvoice([{price: 50, quantity: 2}], {discountPercent: 20, taxPercent: 10}),
        {subtotal: 100, shipping: 0, total: 88});
});
test('invoice below threshold includes shipping after tax', () => {
    assert.deepEqual(createInvoice([{price: 25, quantity: 2}], {discountPercent: 10, taxPercent: 10}),
        {subtotal: 50, shipping: 10, total: 59.5});
});
"""


def prepare(parent, node=None):
    node = node or shutil.which("node")
    if not node:
        raise ValueError("JavaScript presentation requires Node.js on PATH. The offline Python Demo is still available with make run.")
    repo = Path(parent).resolve() / ("javascript-" + uuid.uuid4().hex[:12])
    repo.mkdir(parents=True, exist_ok=False)
    (repo / "tests").mkdir()
    (repo / "invoice.js").write_text(SOURCE)
    (repo / "tests/invoice.test.js").write_text(TESTS)
    (repo / "README.md").write_text("# Live debugging practice\n\n" + ISSUE + "\n\nRun: node --test tests/invoice.test.js\n\nThis is an intentionally broken synthetic example, not a benchmark.\n")
    git(repo, "init")
    git(repo, "config", "user.name", "RAKSHAK Presentation")
    git(repo, "config", "user.email", "presentation@example.invalid")
    git(repo, "add", "invoice.js", "tests/invoice.test.js", "README.md")
    git(repo, "-c", "commit.gpgsign=false", "commit", "-m", "Fresh intentionally failing presentation example")
    return {"repo": str(repo), "test": [str(Path(node).resolve()), "--test", "tests/invoice.test.js"], "issue": ISSUE}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "build/presentations")
    args = parser.parse_args()
    config = prepare(args.output)
    print(json.dumps(config, indent=2), flush=True)
    if args.prepare_only:
        return
    env = dict(os.environ, HARNESS_REPO=config["repo"], HARNESS_TEST=json.dumps(config["test"]), HARNESS_ISSUE=config["issue"])
    # Do not change the prescribed provider/model or persist the runtime key.
    os.execve(sys.executable, [sys.executable, "-m", "harness", "tui"], env)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc))
