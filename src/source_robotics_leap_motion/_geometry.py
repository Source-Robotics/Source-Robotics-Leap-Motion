"""Small quaternion operations, independent of numerical or robot SDKs."""

import math

from .models import Quaternion, Vector3


def rotate(q: Quaternion, v: Vector3) -> Vector3:
    q = unit(q.x, q.y, q.z, q.w)
    t = Vector3(q.y * v.z - q.z * v.y, q.z * v.x - q.x * v.z, q.x * v.y - q.y * v.x) * 2
    return (
        v + t * q.w + Vector3(q.y * t.z - q.z * t.y, q.z * t.x - q.x * t.z, q.x * t.y - q.y * t.x)
    )


def unit(x: float, y: float, z: float, w: float) -> Quaternion:
    length = math.sqrt(x * x + y * y + z * z + w * w)
    return Quaternion(x / length, y / length, z / length, w / length)


def inverse(q: Quaternion) -> Quaternion:
    return unit(-q.x, -q.y, -q.z, q.w)


def multiply(a: Quaternion, b: Quaternion) -> Quaternion:
    return unit(
        a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
        a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
        a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
        a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z,
    )


def angle(a: Quaternion, b: Quaternion) -> float:
    a = unit(a.x, a.y, a.z, a.w)
    b = unit(b.x, b.y, b.z, b.w)
    dot = abs(a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w)
    return 2 * math.acos(min(1.0, dot))


def slerp(a: Quaternion, b: Quaternion, fraction: float) -> Quaternion:
    a = unit(a.x, a.y, a.z, a.w)
    b = unit(b.x, b.y, b.z, b.w)
    av = (a.x, a.y, a.z, a.w)
    bv = (b.x, b.y, b.z, b.w)
    dot = sum(x * y for x, y in zip(av, bv, strict=True))
    if dot < 0:
        bv = tuple(-value for value in bv)
        dot = -dot
    if dot > 0.9995:
        return unit(*(x + fraction * (y - x) for x, y in zip(av, bv, strict=True)))
    theta = math.acos(min(1.0, dot))
    left = math.sin((1 - fraction) * theta) / math.sin(theta)
    right = math.sin(fraction * theta) / math.sin(theta)
    return unit(*(left * x + right * y for x, y in zip(av, bv, strict=True)))


def power(q: Quaternion, gain: float) -> Quaternion:
    q = unit(q.x, q.y, q.z, q.w)
    sign = 1 if q.w >= 0 else -1
    sine = math.sqrt(q.x * q.x + q.y * q.y + q.z * q.z)
    if sine < 1e-12:
        return Quaternion()
    half_angle = math.atan2(sine, abs(q.w)) * gain
    scale = sign * math.sin(half_angle) / sine
    return unit(q.x * scale, q.y * scale, q.z * scale, math.cos(half_angle))


def axis_rotation(axes: tuple[str, str, str]) -> Quaternion:
    matrix = [[0.0] * 3 for _ in range(3)]
    for row, axis in enumerate(axes):
        matrix[row]["xyz".index(axis.lstrip("-"))] = -1 if axis.startswith("-") else 1
    trace = sum(matrix[i][i] for i in range(3))
    if trace > 0:
        scale = math.sqrt(trace + 1) * 2
        return unit(
            (matrix[2][1] - matrix[1][2]) / scale,
            (matrix[0][2] - matrix[2][0]) / scale,
            (matrix[1][0] - matrix[0][1]) / scale,
            scale / 4,
        )
    i = max(range(3), key=lambda j: matrix[j][j])
    j, k = (i + 1) % 3, (i + 2) % 3
    scale = math.sqrt(1 + matrix[i][i] - matrix[j][j] - matrix[k][k]) * 2
    values = [0.0] * 4
    values[i] = scale / 4
    values[j] = (matrix[j][i] + matrix[i][j]) / scale
    values[k] = (matrix[k][i] + matrix[i][k]) / scale
    values[3] = (matrix[k][j] - matrix[j][k]) / scale
    return unit(*values)
