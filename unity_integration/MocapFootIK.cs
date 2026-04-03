using UnityEngine;

/// <summary>
/// Mocap Foot IK 算法模块
/// 解决单目动捕中常见的“滑步(Foot Sliding)”和“浮空”问题。
/// 通过速度推断接触状态，结合射线检测，利用 Unity Animator IK 将脚部牢牢锁定在地形表面，并智能修正骨盆高度。
/// 注意：请在 Animator 组件中开启图层的 "IK Pass" 选项。
/// </summary>
[RequireComponent(typeof(Animator))]
public class MocapFootIK : MonoBehaviour
{
    private Animator animator;

    [Header("IK Settings")]
    [Range(0, 1)] public float ikWeight = 1f;       // 全局 IK 权重
    public LayerMask groundLayer = ~0;              // 识别为地面的图层
    public float raycastUpOffset = 0.5f;            // 射线起点向上偏移，防止脚穿入地下导致检测失败
    public float raycastDownDistance = 1.0f;        // 射线向下探测的距离

    [Header("Contact Detection Algorithm")]
    public float velocityThreshold = 0.05f;         // 速度阈值：低于此速度认为脚已落地静止
    public float groundedTransitionSpeed = 5.0f;    // 接触状态(IK权重)的过渡平滑速度

    [Header("Hips Correction")]
    public bool enableHipsCorrection = true;        // 是否自动压低骨盆避免腿被拉直

    // 脚踝到脚底的偏移距离 (防止脚踝直接陷进地表)
    private float leftFootHeightOffset;
    private float rightFootHeightOffset;

    // 历史位置，用于计算速度
    private Vector3 lastLeftFootPos;
    private Vector3 lastRightFootPos;

    // 动态接触权重 (0~1)
    private float leftFootWeight = 0f;
    private float rightFootWeight = 0f;

    void Start()
    {
        animator = GetComponent<Animator>();

        if (animator == null || !animator.isHuman)
        {
            Debug.LogError("[Mocap IK] 未找到 Humanoid Animator 组件！");
            this.enabled = false;
            return;
        }

        // 自动计算脚踝到地面的初始距离作为 Offset (假设 T-Pose 时脚踩在模型原点地平面上)
        Transform lFoot = animator.GetBoneTransform(HumanBodyBones.LeftFoot);
        Transform rFoot = animator.GetBoneTransform(HumanBodyBones.RightFoot);

        leftFootHeightOffset = lFoot != null ? lFoot.position.y - transform.position.y : 0.1f;
        rightFootHeightOffset = rFoot != null ? rFoot.position.y - transform.position.y : 0.1f;

        // 保证偏移量不为负或过小
        leftFootHeightOffset = Mathf.Max(0.05f, leftFootHeightOffset);
        rightFootHeightOffset = Mathf.Max(0.05f, rightFootHeightOffset);
    }

    void Update()
    {
        // 1. 接触状态机算法 (Contact State Machine)
        // 通过实时计算脚踝的世界空间速度，来推断是否属于“踩实”状态。
        Transform lFoot = animator.GetBoneTransform(HumanBodyBones.LeftFoot);
        Transform rFoot = animator.GetBoneTransform(HumanBodyBones.RightFoot);

        if (lFoot != null && rFoot != null)
        {
            float lVelocity = (lFoot.position - lastLeftFootPos).magnitude / Time.deltaTime;
            float rVelocity = (rFoot.position - lastRightFootPos).magnitude / Time.deltaTime;

            // 目标权重：低于速度阈值则视为接触(1)，否则视为离地悬空(0)
            float targetLeftWeight = lVelocity < velocityThreshold ? 1f : 0f;
            float targetRightWeight = rVelocity < velocityThreshold ? 1f : 0f;

            // 运用平滑过渡，防止跳跃感
            leftFootWeight = Mathf.Lerp(leftFootWeight, targetLeftWeight, Time.deltaTime * groundedTransitionSpeed);
            rightFootWeight = Mathf.Lerp(rightFootWeight, targetRightWeight, Time.deltaTime * groundedTransitionSpeed);

            // 更新历史位置
            lastLeftFootPos = lFoot.position;
            lastRightFootPos = rFoot.position;
        }
    }

    void OnAnimatorIK(int layerIndex)
    {
        if (animator == null) return;

        // 统一控制全局 IK 权重
        animator.SetIKPositionWeight(AvatarIKGoal.LeftFoot, leftFootWeight * ikWeight);
        animator.SetIKRotationWeight(AvatarIKGoal.LeftFoot, leftFootWeight * ikWeight);

        animator.SetIKPositionWeight(AvatarIKGoal.RightFoot, rightFootWeight * ikWeight);
        animator.SetIKRotationWeight(AvatarIKGoal.RightFoot, rightFootWeight * ikWeight);

        // 如果权重极小，直接跳过复杂射线计算以节省性能
        if (ikWeight <= 0f) return;

        // 计算左脚的 IK 目标位置与旋转
        float leftHipsOffset = 0f;
        if (leftFootWeight > 0.01f)
        {
            leftHipsOffset = ApplyFootIK(AvatarIKGoal.LeftFoot, leftFootHeightOffset, ref leftFootWeight);
        }

        // 计算右脚的 IK 目标位置与旋转
        float rightHipsOffset = 0f;
        if (rightFootWeight > 0.01f)
        {
            rightHipsOffset = ApplyFootIK(AvatarIKGoal.RightFoot, rightFootHeightOffset, ref rightFootWeight);
        }

        // 3. 骨盆修正算法 (Hips Pull-down)
        // 当脚部被强制吸附在地面上时，如果原始骨盆太高，会导致腿被拉长变形。
        // 我们取两脚被吸附时所需的“最大下沉量”，将骨盆整体压低。
        if (enableHipsCorrection)
        {
            float totalHipsCorrection = Mathf.Min(leftHipsOffset, rightHipsOffset);
            if (totalHipsCorrection < -0.01f)
            {
                // 将补偿值应用到 BodyPosition (骨盆位置)
                Vector3 currentHipsPos = animator.bodyPosition;
                currentHipsPos.y += totalHipsCorrection;
                animator.bodyPosition = currentHipsPos;
            }
        }
    }

    /// <summary>
    /// 对单脚进行射线检测并应用 IK
    /// </summary>
    /// <returns>返回高度差(offset)用于修正骨盆</returns>
    private float ApplyFootIK(AvatarIKGoal footGoal, float footOffset, ref float currentWeight)
    {
        Vector3 targetIKPos = animator.GetIKPosition(footGoal);
        Quaternion targetIKRot = animator.GetIKRotation(footGoal);

        // 射线起点：脚上方一定高度，防止射线发射点在地下
        Vector3 rayOrigin = targetIKPos + Vector3.up * raycastUpOffset;
        RaycastHit hit;

        if (Physics.Raycast(rayOrigin, Vector3.down, out hit, raycastDownDistance + raycastUpOffset, groundLayer))
        {
            // 找到地面
            // 新位置：碰撞点坐标 + 抵消脚踝高度的偏移量
            Vector3 footPosition = hit.point;
            footPosition.y += footOffset;

            // 新旋转：根据地表法线调整脚部角度（例如踩在斜坡上）
            // 构造新的正交基使得脚的 Y 轴(上)与地面法线对齐
            Vector3 forward = Vector3.ProjectOnPlane(targetIKRot * Vector3.forward, hit.normal);
            Quaternion footRotation = Quaternion.LookRotation(forward, hit.normal);

            animator.SetIKPosition(footGoal, footPosition);
            animator.SetIKRotation(footGoal, footRotation);

            // 计算该脚产生的误差：如果地面(footPosition.y)比原动画预期(targetIKPos.y)低，
            // 会导致脚拉长。我们返回这个差值用于拉低骨盆。
            return footPosition.y - targetIKPos.y;
        }
        else
        {
            // 没有检测到地面（比如跳出悬崖），取消这只脚的 IK 权重
            currentWeight = 0f;
            animator.SetIKPositionWeight(footGoal, 0f);
            animator.SetIKRotationWeight(footGoal, 0f);
            return 0f;
        }
    }
}
