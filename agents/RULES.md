# TransZKEval Circom Knowledge Rules

These are the 20 rules used by the `knowledge` strategy in the TransZKEval translation experiments.

## 1. The Zero-Jump Rule (Branching)

In ZK circuits, there is no instruction pointer jump. Both `if` and `else` paths are executed. You must compute both results and use a binary selector signal (`0` or `1`) to pick the valid output.

## 2. Quadratic Constraint Limit (R1CS)

Circom constraints (`<==` or `===`) must be quadratic. You cannot multiply three or more signals directly.

- Wrong: `out <== a * b * c;`
- Correct: `signal intermediate <== a * b; out <== intermediate * c;`

## 3. Verification over Calculation (Division/Mod)

You cannot calculate division (`/`) or modulo (`%`) directly in a constraint. You must provide the answer as a witness and verify it via a linear equation.

- Pattern: `Dividend === Divisor * Quotient + Remainder;`
- Constraint: use `<--` for the witness assignment and `===` for enforcement.

## 4. Field Element Awareness (Negative Numbers)

Circom operates in a prime field `F_p`. A negative number `-x` is represented as `P - x`, which is a very large positive number. To compare `a < b` where `a` might be negative, use `Num2Bits` to check the sign bit (bit 253) or shift values into a safe range.

## 5. Absolute Value Shielding

When performing division or scaling on signed numbers, follow this pipeline to avoid field overflow errors:

1. Extract the sign bit with `Num2Bits(254)`.
2. Convert to absolute value: `abs <== sign * (-2 * val) + val;`
3. Perform unsigned arithmetic (division or modulo) on `abs`.
4. Reapply the sign: `out <== (1 - 2 * sign) * abs_result;`

## 6. Signal Immutability

Signals are constants once assigned. If you need to update a value in a loop, such as an accumulator, use a `var` for intermediate calculation or a signal array (`s[i]`) for sequential constraints.

## 7. Bit-Length Safety (Aliasing)

Always specify the bit length in comparators, for example `LessThan(252)`. Using the full 254 bits of the prime field can cause aliasing, where a value wraps around the prime `P`. A 252-bit width is the standard safety limit.

## 8. Boolean Logic Arithmetization

Translate logical gates into polynomials:

- `NOT(a)` becomes `1 - a`
- `AND(a, b)` becomes `a * b`
- `OR(a, b)` becomes `a + b - a * b`

## 9. Priority Chains (Else-If Logic)

To simulate `if-else if-else`, make selectors mutually exclusive so results are not added together.

```circom
isA <== condA;
isB <== (1 - isA) * condB;
isC <== (1 - isA) * (1 - isB);
```

## 10. The Zero-Division Trap

Always handle a potentially zero divisor with the `IsZero()` component. Division by zero during witness generation (`<--`) can crash the prover or produce an invalid proof.

## 11. Integer Scaling (Fixed-Point)

ZK circuits do not support floating-point numbers. Multiply values by a large power of ten before dividing to preserve precision. Use `(numerator * scale) / denominator`.

## 12. Linear vs. Non-Linear Constraints

Multiplying a signal by a constant, such as `out <== a * 5;`, is a linear constraint and is computationally cheap. Multiplying two signals, such as `out <== a * b;`, is non-linear and increases proof size.

## 13. Witness vs. Constraint Separation

Use `<--` for values that are expensive to compute but easy to verify, such as square roots or private hints. Always follow the witness assignment with a `===` constraint so the prover cannot lie.

## 14. Range Proofs

Always enforce that inputs remain within their expected bounds, such as `0` through `2^32 - 1`. Never assume an input is small; in `F_p`, it may be a malicious large value.

## 15. The Mux Formula (Standard Selection)

For `res = condition ? a : b`, use the optimized quadratic form:

```circom
out <== condition * (a - b) + b;
```

## 16. Component Encapsulation

Keep templates small and modular. If a piece of logic involves more than 5–10 complex constraints, put it in a separate `template` to improve readability and debugging.

## 17. Constant Bit-Widths

When using `Num2Bits(n)`, `n` must be a constant known at compile time. Dynamic bit widths are unsupported.

## 18. Avoid Nested Signal Declarations

Do not declare `signal` or `component` inside a `for` loop that depends on an input variable. Declare all signals in the top-level template scope or as fixed-size arrays.

## 19. Underflow Awareness

In `F_p`, `3 - 5` produces `P - 2`, rather than the ordinary integer `-2`. Addition and subtraction still work, but comparisons break. Use comparators designed for field elements.

## 20. Deterministic Constraints

Every output signal must be constrained to a unique value. An unconstrained output lets a malicious prover choose any value, breaking circuit soundness.
