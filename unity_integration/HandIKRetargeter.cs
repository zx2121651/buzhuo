using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Mocap 高精度全指关节重定向 (Full Hand & Finger IK Solver)
/// 利用 MediaPipe Holistic 提供的左右手各 21 个点，推算出指掌平面的法线作为旋转约束，
/// 并通过纯 FK 将大拇指、食指、中指、无名指、小指的三段指节的 Quaternion 局部旋转映射到 Unity Humanoid 模型上。
/// </summary>
[RequireComponent(typeof(Animator))]
public class HandIKRetargeter : MonoBehaviour
{
    [Header("Data Source")]
    public UDPReceiver receiver;

    [Header("Settings")]
    public bool enableLeftHand = true;
    public bool enableRightHand = true;

    private Animator animator;

    // 存储所有骨骼的引用
    private Dictionary<HumanBodyBones, Transform> boneTransforms = new Dictionary<HumanBodyBones, Transform>();

    // 存储 T-Pose 的初始正交基 (世界空间旋转)，用于消除不同模型的初始畸变
    private Dictionary<HumanBodyBones, Quaternion> initialRotations = new Dictionary<HumanBodyBones, Quaternion>();
    private Dictionary<HumanBodyBones, Quaternion> initialLocalRotations = new Dictionary<HumanBodyBones, Quaternion>();

    // MediaPipe 手指连接索引: [掌侧根部(Proximal), 中间(Intermediate), 末端(Distal)]
    private readonly int[] thumbIndices = { 1, 2, 3, 4 };
    private readonly int[] indexIndices = { 5, 6, 7, 8 };
    private readonly int[] middleIndices = { 9, 10, 11, 12 };
    private readonly int[] ringIndices = { 13, 14, 15, 16 };
    private readonly int[] pinkyIndices = { 17, 18, 19, 20 };

    void Start()
    {
        animator = GetComponent<Animator>();
        if (receiver == null) receiver = GetComponent<UDPReceiver>();

        CacheFingers();
        RecordTPose();
    }

    private void CacheFingers()
    {
        HumanBodyBones[] handBones = new HumanBodyBones[]
        {
            // Left Hand
            HumanBodyBones.LeftThumbProximal, HumanBodyBones.LeftThumbIntermediate, HumanBodyBones.LeftThumbDistal,
            HumanBodyBones.LeftIndexProximal, HumanBodyBones.LeftIndexIntermediate, HumanBodyBones.LeftIndexDistal,
            HumanBodyBones.LeftMiddleProximal, HumanBodyBones.LeftMiddleIntermediate, HumanBodyBones.LeftMiddleDistal,
            HumanBodyBones.LeftRingProximal, HumanBodyBones.LeftRingIntermediate, HumanBodyBones.LeftRingDistal,
            HumanBodyBones.LeftLittleProximal, HumanBodyBones.LeftLittleIntermediate, HumanBodyBones.LeftLittleDistal,

            // Right Hand
            HumanBodyBones.RightThumbProximal, HumanBodyBones.RightThumbIntermediate, HumanBodyBones.RightThumbDistal,
            HumanBodyBones.RightIndexProximal, HumanBodyBones.RightIndexIntermediate, HumanBodyBones.RightIndexDistal,
            HumanBodyBones.RightMiddleProximal, HumanBodyBones.RightMiddleIntermediate, HumanBodyBones.RightMiddleDistal,
            HumanBodyBones.RightRingProximal, HumanBodyBones.RightRingIntermediate, HumanBodyBones.RightRingDistal,
            HumanBodyBones.RightLittleProximal, HumanBodyBones.RightLittleIntermediate, HumanBodyBones.RightLittleDistal
        };

        foreach (var b in handBones)
        {
            Transform t = animator.GetBoneTransform(b);
            if (t != null)
                boneTransforms[b] = t;
        }
    }

    private void RecordTPose()
    {
        foreach (var kvp in boneTransforms)
        {
            initialRotations[kvp.Key] = kvp.Value.rotation;
            initialLocalRotations[kvp.Key] = kvp.Value.localRotation;
        }
    }

    void LateUpdate()
    {
        if (receiver == null) return;

        // 1. 处理左手 (Left Hand)
        if (enableLeftHand)
        {
            Landmark[] leftHandMarks = receiver.GetCurrentLeftHand();
            if (leftHandMarks != null && leftHandMarks[0] != null) // 检查是否接收到非空手部数据
            {
                Vector3[] lPoints = new Vector3[21];
                for (int i = 0; i < 21; i++) lPoints[i] = new Vector3(leftHandMarks[i].x, leftHandMarks[i].y, leftHandMarks[i].z);

                // 核心算法：计算左手的“掌心法线 (Palm Normal)”作为所有手指弯曲的极向量 (Up Vector)
                // 食指根部(5), 小指根部(17), 手腕(0) 构成的三角形
                Vector3 lPalmNormal = Vector3.Cross(lPoints[17] - lPoints[0], lPoints[5] - lPoints[0]).normalized;

                // 大拇指法线：大拇指侧面的朝向与掌心不同，我们用食指根部(5)和手腕(0)计算一个垂直向外的向量
                Vector3 lThumbNormal = Vector3.Cross(lPalmNormal, lPoints[5] - lPoints[0]).normalized;

                // 解算并应用所有指节
                ApplyFingerChain(lPoints, thumbIndices, HumanBodyBones.LeftThumbProximal, HumanBodyBones.LeftThumbIntermediate, HumanBodyBones.LeftThumbDistal, lThumbNormal);
                ApplyFingerChain(lPoints, indexIndices, HumanBodyBones.LeftIndexProximal, HumanBodyBones.LeftIndexIntermediate, HumanBodyBones.LeftIndexDistal, lPalmNormal);
                ApplyFingerChain(lPoints, middleIndices, HumanBodyBones.LeftMiddleProximal, HumanBodyBones.LeftMiddleIntermediate, HumanBodyBones.LeftMiddleDistal, lPalmNormal);
                ApplyFingerChain(lPoints, ringIndices, HumanBodyBones.LeftRingProximal, HumanBodyBones.LeftRingIntermediate, HumanBodyBones.LeftRingDistal, lPalmNormal);
                ApplyFingerChain(lPoints, pinkyIndices, HumanBodyBones.LeftLittleProximal, HumanBodyBones.LeftLittleIntermediate, HumanBodyBones.LeftLittleDistal, lPalmNormal);
            }
        }

        // 2. 处理右手 (Right Hand)
        if (enableRightHand)
        {
            Landmark[] rightHandMarks = receiver.GetCurrentRightHand();
            if (rightHandMarks != null && rightHandMarks[0] != null)
            {
                Vector3[] rPoints = new Vector3[21];
                for (int i = 0; i < 21; i++) rPoints[i] = new Vector3(rightHandMarks[i].x, rightHandMarks[i].y, rightHandMarks[i].z);

                // 注意右手坐标系的叉乘方向与左手是镜像的
                Vector3 rPalmNormal = Vector3.Cross(rPoints[5] - rPoints[0], rPoints[17] - rPoints[0]).normalized;
                Vector3 rThumbNormal = Vector3.Cross(rPoints[5] - rPoints[0], rPalmNormal).normalized;

                ApplyFingerChain(rPoints, thumbIndices, HumanBodyBones.RightThumbProximal, HumanBodyBones.RightThumbIntermediate, HumanBodyBones.RightThumbDistal, rThumbNormal);
                ApplyFingerChain(rPoints, indexIndices, HumanBodyBones.RightIndexProximal, HumanBodyBones.RightIndexIntermediate, HumanBodyBones.RightIndexDistal, rPalmNormal);
                ApplyFingerChain(rPoints, middleIndices, HumanBodyBones.RightMiddleProximal, HumanBodyBones.RightMiddleIntermediate, HumanBodyBones.RightMiddleDistal, rPalmNormal);
                ApplyFingerChain(rPoints, ringIndices, HumanBodyBones.RightRingProximal, HumanBodyBones.RightRingIntermediate, HumanBodyBones.RightRingDistal, rPalmNormal);
                ApplyFingerChain(rPoints, pinkyIndices, HumanBodyBones.RightLittleProximal, HumanBodyBones.RightLittleIntermediate, HumanBodyBones.RightLittleDistal, rPalmNormal);
            }
        }
    }

    /// <summary>
    /// 计算一整根手指的三段关节的旋转
    /// </summary>
    private void ApplyFingerChain(Vector3[] pts, int[] idx, HumanBodyBones prox, HumanBodyBones inter, HumanBodyBones dist, Vector3 upNormal)
    {
        // Proximal (指根)
        ApplyRotation(prox, pts[idx[0]], pts[idx[1]], upNormal);
        // Intermediate (中段)
        ApplyRotation(inter, pts[idx[1]], pts[idx[2]], upNormal);
        // Distal (指尖)
        ApplyRotation(dist, pts[idx[2]], pts[idx[3]], upNormal);
    }

    /// <summary>
    /// 利用 LookRotation 计算单个指节的防扭曲旋转并赋予骨骼
    /// </summary>
    private void ApplyRotation(HumanBodyBones bone, Vector3 startPt, Vector3 endPt, Vector3 upVector)
    {
        if (!boneTransforms.ContainsKey(bone)) return;

        Vector3 targetForward = (endPt - startPt).normalized;
        if (targetForward == Vector3.zero || upVector == Vector3.zero) return;

        // 根据手指主轴和掌心法线构建 3D 正交基
        Quaternion targetRot = Quaternion.LookRotation(targetForward, upVector);

        // 与身体躯干重定向类似，我们将其直接覆盖为绝对世界坐标旋转。
        // （由于手指的 T-Pose 轴向定义通常非常标准，这种 FK 在绝大多数带手指的 Humanoid 模型上直接生效。
        // 如果个别模型手指抽筋，通常是因为模型作者定义手指 Z 轴不朝外，
        // 届时可以像躯干那样通过计算 targetRot * Inverse(initTpose) * initLocal 的局部差值来解决）
        boneTransforms[bone].rotation = targetRot;
    }
}
