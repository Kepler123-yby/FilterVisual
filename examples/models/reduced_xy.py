"""Four-state XY CV example: assumes fixed plate orientation and known geometry."""
import numpy as np
from scipy.linalg import block_diag
from filtervisual.models.protocol import AngularModel
from filtervisual.core.types import PhysicalEstimate, TruthMapping


class XYModel(AngularModel):
    state_names = ("cx", "cy", "vx", "vy")
    units = ("m", "m", "m/s", "m/s")
    angular_indices = ()

    def __init__(self, geometry, q=.2, position_std=.01, yaw_std=.02, reference_yaw=0.):
        self.geometry=geometry
        self.q=q
        self.position_std=position_std
        self.yaw_std=yaw_std
        self.reference_yaw=reference_yaw

    def f(self,x,dt,t0):
        y=x.copy()
        y[:2]+=y[2:]*dt
        return y

    def jacobian_f(self,x,dt,t0):
        F=np.eye(4);F[0,2]=F[1,3]=dt
        return F

    def Q(self,dt):
        Q=np.zeros((4,4))
        block=self.q*np.array([[dt**3/3,dt**2/2],[dt**2/2,dt]])
        Q[np.ix_([0,2],[0,2])]=block
        Q[np.ix_([1,3],[1,3])]=block
        return Q

    def h(self,x,context):
        values=[]
        g=self.geometry
        for plate in context.plate_ids:
            yaw=self.reference_yaw+(plate-g.reference_id)*np.pi/2
            radius=g.radius_b if plate%2 else g.radius_a
            values.extend([x[0]+radius*np.cos(yaw),x[1]+radius*np.sin(yaw),
                           g.height_a+(g.height_diff if plate%2 else 0),yaw])
        return np.array(values)

    def jacobian_h(self,x,context):
        H=np.zeros((4*len(context.plate_ids),4))
        for i in range(len(context.plate_ids)):
            H[4*i,0]=H[4*i+1,1]=1
        return H

    def R(self,frame):
        R=np.diag([self.position_std**2]*3+[self.yaw_std**2])
        return block_diag(*[R for _ in frame.context.plate_ids])

    def project(self,x,P):
        # No armor projection or orientation is claimed by this reduced model.
        return PhysicalEstimate(center_xy=x[:2].copy(),velocity_xyz=np.r_[x[2:],0.],
                                covariance={"center_xy":P[:2,:2].copy()})

    def truth_mapping(self,physical):
        return TruthMapping(indices=(0,1,2,3),values=np.r_[physical.center_xy,physical.velocity_xyz[:2]])


def build_model(params,geometry):
    return XYModel(geometry,**params)
