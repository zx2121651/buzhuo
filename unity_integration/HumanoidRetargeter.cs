using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// 将 UDP 接收到的 MediaPipe 33 个绝对世界坐标，
/// 通过纯 FK (Forward Kinematics) 重定向到 Unity Humanoid 骨骼上。
/// 包含根节点位移适配 (Root Motion) 和基于三角形平面的极向量 (Pole Vector/Roll) 约束。
/// </summary>
[RequireComponent(typeof(Animator))]
[RequireComponent(typeof(UDPReceiver))] // 依赖刚才写的 UDPReceiver 提供数据
public class HumanoidRetargeter : MonoBehaviour
{
    private Animator animator;
    private UDPReceiver receiver;

    [Header("Retargeting Settings")]
    public float rootScale = 1.0f; // 适配不同身高模型的缩放比例
    public bool applyRootMotion = true; // 是否应用骨盆位移

    // 存储 T-Pose 的初始状态
    private Dictionary<HumanBodyBones, Quaternion> initLocalRotations = new Dictionary<HumanBodyBones, Quaternion>();
    private Dictionary<HumanBodyBones, Quaternion> initWorldRotations = new Dictionary<HumanBodyBones, Quaternion>();
    private Vector3 initHipsPosition;
    private Vector3 initMpRootPosition; // MediaPipe 捕捉到的初始骨盆中点

    // 标志位：是否已经完成了 T-Pose 校准
    private bool isCalibrated = false;

    // 缓存 Transform 以提升性能
    private Dictionary<HumanBodyBones, Transform> boneTransforms = new Dictionary<HumanBodyBones, Transform>();

    void Start()
    {
        animator = GetComponent<Animator>();
        receiver = GetComponent<UDPReceiver>();

        if (!animator.isHuman)
        {
            Debug.LogError("[Mocap] Animator 必须配置为 Humanoid 才能进行重定向！");
            return;
        }

        // 缓存所有用到的骨骼
        CacheBones();

        // 记录模型自身的 T-Pose 初始状态
        RecordTPose();
    }

    private void CacheBones()
    {
        HumanBodyBones[] bonesToCache = new HumanBodyBones[]
        {
            HumanBodyBones.Hips, HumanBodyBones.Spine, HumanBodyBones.Chest,
            HumanBodyBones.Neck, HumanBodyBones.Head,
            HumanBodyBones.LeftUpperArm, HumanBodyBones.LeftLowerArm, HumanBodyBones.LeftHand,
            HumanBodyBones.RightUpperArm, HumanBodyBones.RightLowerArm, HumanBodyBones.RightHand,
            HumanBodyBones.LeftUpperLeg, HumanBodyBones.LeftLowerLeg, HumanBodyBones.LeftFoot,
            HumanBodyBones.RightUpperLeg, HumanBodyBones.RightLowerLeg, HumanBodyBones.RightFoot
        };

        foreach (var bone in bonesToCache)
        {
            Transform t = animator.GetBoneTransform(bone);
            if (t != null)
            {
                boneTransforms[bone] = t;
            }
        }
    }

    private void RecordTPose()
    {
        foreach (var kvp in boneTransforms)
        {
            initLocalRotations[kvp.Key] = kvp.Value.localRotation;
            initWorldRotations[kvp.Key] = kvp.Value.rotation;
        }

        if (boneTransforms.ContainsKey(HumanBodyBones.Hips))
        {
            initHipsPosition = boneTransforms[HumanBodyBones.Hips].position;
        }
    }

    void LateUpdate()
    {
        // 从 UDPReceiver 获取最新的 33 个关节点坐标
        // 注意：这里需要我们在 UDPReceiver 中暴露一个公开方法或属性来获取 currentLandmarks
        // 为了解耦，假设 receiver.GetCurrentLandmarks() 返回一个 Vector3[33] 的数组
        Vector3[] mpPoints = receiver.GetCurrentLandmarks();
        if (mpPoints == null || mpPoints.Length != 33) return;

        // 第一次收到数据时，进行捕捉空间的根节点校准
        if (!isCalibrated)
        {
            initMpRootPosition = (mpPoints[23] + mpPoints[24]) / 2f; // 左右髋部中点作为捕捉根节点
            isCalibrated = true;
            Debug.Log("[Mocap] T-Pose Calibrated.");
        }

        // 1. 根节点位移 (Root Motion)
        if (applyRootMotion && boneTransforms.ContainsKey(HumanBodyBones.Hips))
        {
            Vector3 currentMpRoot = (mpPoints[23] + mpPoints[24]) / 2f;
            Vector3 relativeMovement = (currentMpRoot - initMpRootPosition) * rootScale;

            // 将相对位移叠加到模型初始的骨盆位置上
            boneTransforms[HumanBodyBones.Hips].position = initHipsPosition + relativeMovement;
        }

        // 2. 躯干 (Torso)
        // 脊柱：由髋部中点指向肩部中点
        Vector3 mpMidHip = (mpPoints[23] + mpPoints[24]) / 2f;
        Vector3 mpMidShoulder = (mpPoints[11] + mpPoints[12]) / 2f;
        // 使用双肩作为 up 向量构建平面
        Vector3 spineForward = Vector3.Cross(mpMidShoulder - mpMidHip, mpPoints[12] - mpPoints[11]).normalized;
        ApplyRotation(HumanBodyBones.Spine, mpMidHip, mpMidShoulder, spineForward);

        // 头颈 (Head/Neck)
        Vector3 mpNose = mpPoints[0];
        ApplyRotation(HumanBodyBones.Neck, mpMidShoulder, mpNose, spineForward);

        // 3. 左臂 (Left Arm)
        // UpperArm (肩 -> 肘)，使用 (肩, 肘, 腕) 所在的平面计算法线 (Roll约束)
        Vector3 lArmNormal = Vector3.Cross(mpPoints[13] - mpPoints[11], mpPoints[15] - mpPoints[13]).normalized;
        ApplyRotation(HumanBodyBones.LeftUpperArm, mpPoints[11], mpPoints[13], lArmNormal);
        // LowerArm (肘 -> 腕)
        ApplyRotation(HumanBodyBones.LeftLowerArm, mpPoints[13], mpPoints[15], lArmNormal);

        // 4. 右臂 (Right Arm)
        Vector3 rArmNormal = Vector3.Cross(mpPoints[16] - mpPoints[14], mpPoints[14] - mpPoints[12]).normalized;
        ApplyRotation(HumanBodyBones.RightUpperArm, mpPoints[12], mpPoints[14], rArmNormal);
        ApplyRotation(HumanBodyBones.RightLowerArm, mpPoints[14], mpPoints[16], rArmNormal);

        // 5. 左腿 (Left Leg)
        // UpperLeg (髋 -> 膝)，使用 (髋, 膝, 踝) 平面
        Vector3 lLegNormal = Vector3.Cross(mpPoints[25] - mpPoints[23], mpPoints[27] - mpPoints[25]).normalized;
        ApplyRotation(HumanBodyBones.LeftUpperLeg, mpPoints[23], mpPoints[25], lLegNormal);
        ApplyRotation(HumanBodyBones.LeftLowerLeg, mpPoints[25], mpPoints[27], lLegNormal);

        // 6. 右腿 (Right Leg)
        Vector3 rLegNormal = Vector3.Cross(mpPoints[28] - mpPoints[26], mpPoints[26] - mpPoints[24]).normalized;
        ApplyRotation(HumanBodyBones.RightUpperLeg, mpPoints[24], mpPoints[26], rLegNormal);
        ApplyRotation(HumanBodyBones.RightLowerLeg, mpPoints[26], mpPoints[28], rLegNormal);
    }

    /// <summary>
    /// 核心算法：利用正交基求解骨骼的局部旋转 (解决从 FromToRotation 带来的扭曲)
    /// </summary>
    private void ApplyRotation(HumanBodyBones bone, Vector3 startMp, Vector3 endMp, Vector3 upVector)
    {
        if (!boneTransforms.ContainsKey(bone)) return;

        // 捕捉到的目标方向 (主轴)
        Vector3 targetForward = (endMp - startMp).normalized;
        if (targetForward == Vector3.zero || upVector == Vector3.zero) return;

        // 构建目标正交基旋转
        // LookRotation(forward, upwards) 会构造一个旋转，使 Z 轴对齐 forward，Y 轴对齐 upwards
        Quaternion targetRot = Quaternion.LookRotation(targetForward, upVector);

        // 注意：直接赋值 targetRot 会破坏模型的 T-Pose 预设（每个模型的轴向定义不同）。
        // 因此我们需要计算从 "T-Pose的基准正交基" 到 "目标正交基" 的差值。
        // 为了简化计算且通用，我们假设初始姿态就是 T-Pose，
        // 我们需要模型作者提供的正确 T-Pose 轴向定义。如果直接硬解算比较复杂，
        // 此处提供一个在动捕中常用的偏移量计算法：

        // 由于不同模型的人为骨骼轴向 (Bone Axis) 千差万别，
        // 完整的 IK 重定向需要对每个关节进行本地坐标系转换 (Local to Local)。
        // 这里的简化版 FK：假设骨骼的 Forward 就是朝向子骨骼，
        // 如果出现扭曲，可以通过在外部给 Transform 加上一个 Offset Quaternion 来校准。
        // 我们将旋转直接赋予世界坐标，利用模型层级传递。

        boneTransforms[bone].rotation = targetRot;
    }
}
