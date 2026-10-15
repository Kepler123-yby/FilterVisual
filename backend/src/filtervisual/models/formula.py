"""Models authored with named states and scalar formulas in the web form.

Formulas are interpreted from a small arithmetic AST. They never execute Python
source, expose attributes, or receive the simulator's unobserved truth values.
"""
from __future__ import annotations

import ast
import keyword
import math
import operator
import re

import numpy as np

from filtervisual.core.linalg import validate_covariance
from filtervisual.core.types import PhysicalEstimate, TruthMapping
from filtervisual.models.protocol import AngularModel
from filtervisual.scene.geometry import armor_positions


_FUNCTIONS = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "exp": math.exp,
    "sqrt": math.sqrt, "abs": abs, "min": min, "max": max,
}
_OPERATORS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
}
_GEOMETRY_NAMES = {"radius_a", "radius_b", "height_a", "height_diff", "reference_id", "pi"}
_PLATE_NAMES = {"plate_id", "plate_offset", "plate_odd", "plate_radius", "plate_height"}
_RESERVED_NAMES = _GEOMETRY_NAMES | _PLATE_NAMES | {"dt", "t0"} | set(_FUNCTIONS)
_TRUTH_ROLES = {"cx", "cy", "zA", "vx", "vy", "vz", "theta", "omega", "rA", "rB", "dh"}
_SCALAR_ROLES = {
    "zA": "height_a", "theta": "reference_yaw", "omega": "angular_velocity",
    "rA": "radius_a", "rB": "radius_b", "dh": "height_diff",
}


def _finite_number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
        raise ValueError(f"{field} 须为有限数值")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{field} 须为有限数值") from error
    if not math.isfinite(result):
        raise ValueError(f"{field} 须为有限数值")
    return result


class _Expression:
    def __init__(self, expression, names, field):
        self.field = field
        if not isinstance(expression, str) or not expression.strip() or len(expression) > 512:
            raise ValueError(f"{field} 须为 1…512 字符的算术表达式")
        try:
            self.tree = ast.parse(expression.strip(), mode="eval").body
        except (SyntaxError, ValueError, RecursionError) as error:
            raise ValueError(f"{field} 表达式语法错误：{getattr(error, 'msg', str(error))}") from error
        if sum(1 for _ in ast.walk(self.tree)) > 128:
            raise ValueError(f"{field} 表达式过于复杂")
        self._validate(self.tree, names)

    def _validate(self, node, names):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            _finite_number(node.value, self.field)
        elif isinstance(node, ast.Name):
            if node.id not in names:
                raise ValueError(f"{self.field} 未知变量「{node.id}」")
        elif isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            self._validate(node.left, names)
            self._validate(node.right, names)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            self._validate(node.operand, names)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS:
            if node.keywords or not node.args or (node.func.id not in ("min", "max") and len(node.args) != 1):
                raise ValueError(f"{self.field} 函数「{node.func.id}」参数数量不正确")
            # min/max take scalar arguments rather than Python's iterable form.
            if node.func.id in ("min", "max") and len(node.args) < 2:
                raise ValueError(f"{self.field} 函数「{node.func.id}」至少需要两个数值参数")
            for argument in node.args:
                self._validate(argument, names)
        else:
            raise ValueError(f"{self.field} 仅支持数值、变量、算术运算和 sin/cos/tan/exp/sqrt/abs/min/max")

    def __call__(self, values):
        def evaluate(node):
            if isinstance(node, ast.Constant):
                return float(node.value)
            if isinstance(node, ast.Name):
                return values[node.id]
            if isinstance(node, ast.BinOp):
                return _OPERATORS[type(node.op)](evaluate(node.left), evaluate(node.right))
            if isinstance(node, ast.UnaryOp):
                value = evaluate(node.operand)
                return -value if isinstance(node.op, ast.USub) else value
            return _FUNCTIONS[node.func.id](*(evaluate(argument) for argument in node.args))

        try:
            result = float(evaluate(self.tree))
            if not math.isfinite(result):
                raise ValueError("结果不是有限实数")
            return result
        except (ArithmeticError, TypeError, ValueError) as error:
            raise ValueError(f"{self.field} 计算失败：{error}") from error


class FormulaModel(AngularModel):
    """The fixed four-values-per-plate observation contract with editable formulas."""

    exact_linear_prediction = False

    def __init__(self, params, geometry):
        spec = params.get("form_model") if isinstance(params, dict) else None
        if not isinstance(spec, dict) or type(spec.get("version")) is not int or spec["version"] != 1:
            raise ValueError("form_model.version 须为 1")
        rows = spec.get("states")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 32:
            raise ValueError("状态表须包含 1…32 行")
        self.geometry = geometry.model_copy(deep=True)
        names, units, angular, roles = [], [], [], {}
        for index, row in enumerate(rows):
            field = f"状态第 {index + 1} 行"
            if not isinstance(row, dict):
                raise ValueError(f"{field} 须为状态记录")
            name, unit, role = row.get("name"), row.get("unit"), row.get("truth", "")
            if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name)
                    or keyword.iskeyword(name) or name in _RESERVED_NAMES or name in names):
                raise ValueError(f"{field} 名称须为唯一英文标识符，且不能使用保留名称")
            if not isinstance(unit, str) or len(unit) > 40:
                raise ValueError(f"{field} 单位须为不超过 40 字符的文本")
            if type(row.get("angular")) is not bool:
                raise ValueError(f"{field} 角度标记须为布尔值")
            _finite_number(row.get("initial"), f"{field} 初值")
            if _finite_number(row.get("variance"), f"{field} 初始方差") <= 0:
                raise ValueError(f"{field} 初始方差须大于 0")
            if not isinstance(role, str) or (role and (role not in _TRUTH_ROLES or role in roles)):
                raise ValueError(f"{field} 真值对应须为空或唯一的物理量名称")
            if role:
                required_unit = "rad" if role == "theta" else "rad/s" if role == "omega" else "m/s" if role in ("vx", "vy", "vz") else "m"
                if unit != required_unit:
                    raise ValueError(f"{field} 真值对应 {role} 的单位须为 {required_unit}")
                if role == "theta" and not row["angular"]:
                    raise ValueError(f"{field} 真值对应 theta 须勾选角度标记")
                if role != "theta" and row["angular"]:
                    raise ValueError(f"{field} 真值对应 {role} 不能勾选角度标记")
            names.append(name)
            units.append(unit)
            if row["angular"]:
                angular.append(index)
            if role:
                roles[role] = index
        self.state_names, self.units = tuple(names), tuple(units)
        self.angular_indices, self._roles = tuple(angular), roles
        self._constants = {name: float(getattr(self.geometry, name)) for name in _GEOMETRY_NAMES - {"pi"}}
        self._constants["pi"] = math.pi
        for name, value in self._constants.items():
            _finite_number(value, name)
        state_variables = _GEOMETRY_NAMES | set(names)
        self._transition = tuple(
            _Expression(row.get("transition"), state_variables | {"dt", "t0"}, f"f 状态第 {index + 1} 行 ({names[index]})")
            for index, row in enumerate(rows)
        )
        observations = spec.get("observation")
        if not isinstance(observations, list) or len(observations) != 4:
            raise ValueError("h 观测表须依次填写 x、y、z、yaw 四行")
        self._observation = tuple(
            _Expression(expression, state_variables | _PLATE_NAMES, f"h 观测第 {index + 1} 行")
            for index, expression in enumerate(observations)
        )
        self._q = self._matrix(spec.get("q"), len(names), _GEOMETRY_NAMES | {"dt"}, "Q")
        self._r = self._matrix(spec.get("r"), 4, _GEOMETRY_NAMES, "R")
        # Check the zero-time endpoint as well as representative positive steps.
        for dt in (0., .01, .2):
            self.Q(dt)
        self._r_block = self._evaluate_matrix(self._r, self._constants, "R", positive=True)

    @staticmethod
    def _matrix(rows, dimension, names, field):
        if (not isinstance(rows, list) or len(rows) != dimension
                or any(not isinstance(row, list) or len(row) != dimension for row in rows)):
            raise ValueError(f"{field} 须为 {dimension}×{dimension} 矩阵")
        return tuple(tuple(_Expression(expression, names, f"{field} 第 {i + 1} 行第 {j + 1} 列")
                           for j, expression in enumerate(row)) for i, row in enumerate(rows))

    @staticmethod
    def _evaluate_matrix(expressions, values, field, positive=False):
        result = np.array([[expression(values) for expression in row] for row in expressions])
        try:
            return validate_covariance(result, name=field, positive_definite=positive)
        except ValueError as error:
            requirement = "对称正定" if positive else "对称半正定"
            raise ValueError(f"{field} 须为有限的{requirement}矩阵：{error}") from error

    def _state_values(self, x):
        state = np.asarray(x, dtype=float)
        if state.shape != (len(self.state_names),) or not np.isfinite(state).all():
            raise ValueError(f"状态须为 {len(self.state_names)} 维有限向量")
        return {**self._constants, **dict(zip(self.state_names, map(float, state)))}

    @staticmethod
    def _plate_ids(context):
        ids = tuple(context.plate_ids)
        if (not ids or len(set(ids)) != len(ids)
                or any(isinstance(index, bool) or not isinstance(index, (int, np.integer)) or index not in range(4) for index in ids)):
            raise ValueError("观测装甲板编号须为 0…3 内不重复的整数")
        return ids

    def f(self, x, dt, t0=0.):
        values = self._state_values(x)
        values["dt"], values["t0"] = _finite_number(dt, "dt"), _finite_number(t0, "t0")
        if values["dt"] < 0:
            raise ValueError("dt 须大于或等于 0")
        # Every row reads the old state, independent of row ordering.
        return np.array([expression(values) for expression in self._transition])

    def h(self, x, context):
        values = self._state_values(x)
        observations = []
        for plate_id in self._plate_ids(context):
            odd = int(plate_id) % 2
            plate_values = dict(values, plate_id=float(plate_id), plate_odd=float(odd),
                                plate_offset=(plate_id - self.geometry.reference_id) * math.pi / 2.,
                                plate_radius=self.geometry.radius_b if odd else self.geometry.radius_a,
                                plate_height=self.geometry.height_a + odd * self.geometry.height_diff)
            observations.extend(expression(plate_values) for expression in self._observation)
        return np.asarray(observations)

    def Q(self, dt):
        dt = _finite_number(dt, "Q dt")
        if dt < 0:
            raise ValueError("Q dt 须大于或等于 0")
        return self._evaluate_matrix(self._q, dict(self._constants, dt=dt), "Q")

    def R(self, frame):
        return np.kron(np.eye(len(self._plate_ids(frame.context))), self._r_block)

    def project(self, x, P):
        x, P = np.asarray(x, dtype=float), np.asarray(P, dtype=float)
        if x.shape != (len(self.state_names),) or P.shape != (len(x), len(x)):
            raise ValueError("物理映射的状态或协方差维度不匹配")
        values, covariance = {}, {}
        for role, field in _SCALAR_ROLES.items():
            if role in self._roles:
                index = self._roles[role]
                values[field] = float(x[index])
                covariance[field] = P[index:index + 1, index:index + 1].copy()
        if {"cx", "cy"} <= self._roles.keys():
            indices = [self._roles[role] for role in ("cx", "cy")]
            values["center_xy"] = x[indices].copy()
            covariance["center_xy"] = P[np.ix_(indices, indices)].copy()
        if {"vx", "vy"} <= self._roles.keys():
            roles = ("vx", "vy", "vz") if "vz" in self._roles else ("vx", "vy")
            indices = [self._roles[role] for role in roles]
            values["velocity_xyz"] = np.r_[x[indices], np.zeros(3 - len(indices))]
            covariance["velocity_xyz"] = np.zeros((3, 3))
            covariance["velocity_xyz"][:len(indices), :len(indices)] = P[np.ix_(indices, indices)]
        complete_armor = {"cx", "cy", "zA", "theta", "rA", "rB", "dh"} <= self._roles.keys()
        if not np.isfinite(x).all() or (complete_armor and (values["radius_a"] <= 0 or values["radius_b"] <= 0)):
            return PhysicalEstimate(**values, covariance=covariance, valid=False,
                                    error="物理映射须为有限值，装甲板半径须大于 0")
        if complete_armor:
            geometry = self.geometry.model_copy(update={field: values[field]
                for field in ("height_a", "radius_a", "radius_b", "height_diff")})
            values["armor_positions"] = armor_positions(values["center_xy"], geometry, values["reference_yaw"])
            plate_covariances = []
            for plate_id in range(4):
                odd = plate_id % 2
                yaw = values["reference_yaw"] + (plate_id - self.geometry.reference_id) * math.pi / 2.
                radius_role = "rB" if odd else "rA"
                radius = x[self._roles[radius_role]]
                H = np.zeros((3, len(x)))
                H[0, self._roles["cx"]] = H[1, self._roles["cy"]] = H[2, self._roles["zA"]] = 1.
                H[0, self._roles["theta"]], H[1, self._roles["theta"]] = -radius * math.sin(yaw), radius * math.cos(yaw)
                H[0, self._roles[radius_role]], H[1, self._roles[radius_role]] = math.cos(yaw), math.sin(yaw)
                H[2, self._roles["dh"]] = odd
                plate_covariances.append(H @ P @ H.T)
            covariance["armor_positions"] = np.asarray(plate_covariances)
        return PhysicalEstimate(**values, covariance=covariance)

    def truth_mapping(self, physical):
        indices, values, angular = [], [], []
        for role, index in sorted(self._roles.items(), key=lambda pair: pair[1]):
            if role in ("cx", "cy"):
                value = physical.center_xy[("cx", "cy").index(role)]
            elif role in ("vx", "vy", "vz"):
                value = physical.velocity_xyz[("vx", "vy", "vz").index(role)]
            else:
                value = getattr(physical, _SCALAR_ROLES[role])
            if index in self.angular_indices:
                angular.append(len(indices))
            indices.append(index)
            values.append(value)
        if not indices:
            return None
        return TruthMapping(tuple(indices), np.asarray(values, dtype=float), tuple(angular))
